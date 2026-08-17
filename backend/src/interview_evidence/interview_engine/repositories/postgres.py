"""Tenant-mandatory SQLAlchemy repository for live interviews."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from interview_evidence.interview_engine.domain.session import InterviewSession, SessionState
from interview_evidence.interview_engine.domain.turn import (
    HotViewSyncStatus,
    RecordingChunk,
    SessionCheckpoint,
    Turn,
    TurnSpeaker,
    TurnStatus,
    UploadStatus,
)
from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.database import Base
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class InterviewSessionRow(Base):
    __tablename__ = "interview_sessions"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "interview_session_id",
            name="uq_interview_sessions_company_session",
        ),
    )

    interview_session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invitation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_strategy_id: Mapped[str] = mapped_column(String(36), nullable=False)
    competency_model_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    session_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    row_version: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    degraded_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TurnRow(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "interview_session_id",
            "sequence",
            name="uq_interview_turn_session_sequence",
        ),
        UniqueConstraint(
            "company_id",
            "interview_session_id",
            "idempotency_key",
            name="uq_interview_turn_session_idempotency",
        ),
    )

    turn_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str | None] = mapped_column(Text)
    target_criterion_id: Mapped[str | None] = mapped_column(String(36))
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    model_config_version: Mapped[str | None] = mapped_column(String(128))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionCheckpointRow(Base):
    __tablename__ = "session_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "interview_session_id",
            "session_sequence",
            name="uq_checkpoint_session_sequence",
        ),
    )

    checkpoint_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    last_final_turn_id: Mapped[str | None] = mapped_column(String(36))
    last_media_chunk_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    pending_turn_id: Mapped[str | None] = mapped_column(String(36))
    hot_view_sync_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecordingChunkRow(Base):
    __tablename__ = "recording_chunks"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "interview_session_id",
            "sequence",
            name="uq_recording_chunk_session_sequence",
        ),
        UniqueConstraint(
            "company_id",
            "interview_session_id",
            "idempotency_key",
            name="uq_recording_chunk_session_idempotency",
        ),
    )

    recording_chunk_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    session_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    session_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    upload_status: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InterviewSessionRepository:
    __slots__ = ("session",)

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_session(
        self, context: TenantContext, interview_session: InterviewSession
    ) -> InterviewSession:
        ensure_applicant_scope(context, interview_session.scope)
        self.session.add(self._session_row(interview_session))
        self.session.flush()
        return interview_session

    def get_session(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
    ) -> InterviewSession:
        ensure_applicant_scope(context, scope)
        row = self.session.scalar(
            select(InterviewSessionRow).where(
                InterviewSessionRow.interview_session_id == str(OpaqueId(session_id)),
                InterviewSessionRow.company_id == str(scope.company_id),
                InterviewSessionRow.invitation_id == str(scope.invitation_id),
                InterviewSessionRow.applicant_id == str(scope.applicant_id),
            )
        )
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        return self._session(row)

    def save_session(
        self,
        context: TenantContext,
        interview_session: InterviewSession,
        *,
        expected_row_version: int,
    ) -> InterviewSession:
        ensure_applicant_scope(context, interview_session.scope)
        row = self.session.scalar(
            select(InterviewSessionRow).where(
                InterviewSessionRow.interview_session_id
                == str(interview_session.interview_session_id),
                InterviewSessionRow.company_id == str(interview_session.company_id),
            )
        )
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        if row.row_version != expected_row_version:
            raise SafeApplicationError(ErrorCode.STALE_VERSION, current_version=row.row_version)
        row.state = interview_session.state.value
        row.session_sequence = interview_session.session_sequence
        row.row_version = interview_session.row_version
        row.started_at = interview_session.started_at
        row.completed_at = interview_session.completed_at
        row.degraded_modes = list(interview_session.degraded_modes)
        self.session.flush()
        return interview_session

    def add_turn(self, context: TenantContext, scope: ApplicantScope, turn: Turn) -> Turn:
        self._authorize_child(context, scope, turn.company_id, turn.interview_session_id)
        existing = self.session.scalar(
            select(TurnRow).where(
                TurnRow.company_id == str(scope.company_id),
                TurnRow.interview_session_id == str(turn.interview_session_id),
                TurnRow.idempotency_key == turn.idempotency_key,
            )
        )
        if existing is not None:
            replay = self._turn(existing)
            if replay != turn:
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return replay
        self.session.add(self._turn_row(turn))
        self.session.flush()
        return turn

    def list_turns(
        self, context: TenantContext, scope: ApplicantScope, session_id: str | OpaqueId
    ) -> tuple[Turn, ...]:
        self.get_session(context, scope, session_id)
        rows = self.session.scalars(
            select(TurnRow)
            .where(
                TurnRow.company_id == str(scope.company_id),
                TurnRow.interview_session_id == str(OpaqueId(session_id)),
            )
            .order_by(TurnRow.sequence)
        )
        return tuple(self._turn(row) for row in rows)

    def add_checkpoint(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        checkpoint: SessionCheckpoint,
    ) -> SessionCheckpoint:
        self._authorize_child(
            context, scope, checkpoint.company_id, checkpoint.interview_session_id
        )
        self.session.add(self._checkpoint_row(checkpoint))
        self.session.flush()
        return checkpoint

    def latest_checkpoint(
        self, context: TenantContext, scope: ApplicantScope, session_id: str | OpaqueId
    ) -> SessionCheckpoint | None:
        self.get_session(context, scope, session_id)
        row = self.session.scalars(
            select(SessionCheckpointRow)
            .where(
                SessionCheckpointRow.company_id == str(scope.company_id),
                SessionCheckpointRow.interview_session_id == str(OpaqueId(session_id)),
            )
            .order_by(SessionCheckpointRow.session_sequence.desc())
        ).first()
        return self._checkpoint(row) if row is not None else None

    def add_recording_chunk(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        chunk: RecordingChunk,
    ) -> RecordingChunk:
        self._authorize_child(context, scope, chunk.company_id, chunk.interview_session_id)
        self.session.add(self._chunk_row(chunk))
        self.session.flush()
        return chunk

    def list_recording_chunks(
        self, context: TenantContext, scope: ApplicantScope, session_id: str | OpaqueId
    ) -> tuple[RecordingChunk, ...]:
        self.get_session(context, scope, session_id)
        rows = self.session.scalars(
            select(RecordingChunkRow)
            .where(
                RecordingChunkRow.company_id == str(scope.company_id),
                RecordingChunkRow.interview_session_id == str(OpaqueId(session_id)),
            )
            .order_by(RecordingChunkRow.sequence)
        )
        return tuple(self._chunk(row) for row in rows)

    def relational_target_ids(
        self, context: TenantContext, scope: ApplicantScope
    ) -> tuple[tuple[str, OpaqueId], ...]:
        ensure_applicant_scope(context, scope)
        session_ids = tuple(
            OpaqueId(value)
            for value in self.session.scalars(
                select(InterviewSessionRow.interview_session_id).where(
                    InterviewSessionRow.company_id == str(scope.company_id),
                    InterviewSessionRow.invitation_id == str(scope.invitation_id),
                    InterviewSessionRow.applicant_id == str(scope.applicant_id),
                )
            )
        )
        targets: list[tuple[str, OpaqueId]] = []
        for session_id in session_ids:
            for target_type, row_type, column in (
                ("turn", TurnRow, TurnRow.turn_id),
                ("checkpoint", SessionCheckpointRow, SessionCheckpointRow.checkpoint_id),
                ("recording_chunk", RecordingChunkRow, RecordingChunkRow.recording_chunk_id),
            ):
                targets.extend(
                    (target_type, OpaqueId(value))
                    for value in self.session.scalars(
                        select(column).where(
                            row_type.company_id == str(scope.company_id),
                            row_type.interview_session_id == str(session_id),
                        )
                    )
                )
            targets.append(("interview_session", session_id))
        return tuple(targets)

    def delete_relational_target(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        target_type: str,
        target_id: str | OpaqueId,
    ) -> bool:
        ensure_applicant_scope(context, scope)
        checked_id = str(OpaqueId(target_id))
        table_and_id = {
            "turn": (TurnRow, TurnRow.turn_id),
            "checkpoint": (SessionCheckpointRow, SessionCheckpointRow.checkpoint_id),
            "recording_chunk": (RecordingChunkRow, RecordingChunkRow.recording_chunk_id),
            "interview_session": (InterviewSessionRow, InterviewSessionRow.interview_session_id),
        }.get(target_type)
        if table_and_id is None:
            raise ValueError("unknown interview deletion target type")
        row_type, id_column = table_and_id
        self.session.execute(
            delete(row_type).where(
                id_column == checked_id,
                row_type.company_id == str(scope.company_id),
            )
        )
        self.session.flush()
        return (
            self.session.scalar(
                select(id_column).where(
                    id_column == checked_id,
                    row_type.company_id == str(scope.company_id),
                )
            )
            is None
        )

    def _authorize_child(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        company_id: OpaqueId,
        session_id: OpaqueId,
    ) -> None:
        ensure_applicant_scope(context, scope)
        if company_id != scope.company_id:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        self.get_session(context, scope, session_id)

    @staticmethod
    def _session_row(interview_session: InterviewSession) -> InterviewSessionRow:
        return InterviewSessionRow(
            interview_session_id=str(interview_session.interview_session_id),
            company_id=str(interview_session.scope.company_id),
            invitation_id=str(interview_session.scope.invitation_id),
            applicant_id=str(interview_session.scope.applicant_id),
            interview_strategy_id=str(interview_session.interview_strategy_id),
            competency_model_version_id=str(interview_session.competency_model_version_id),
            state=interview_session.state.value,
            session_sequence=interview_session.session_sequence,
            row_version=interview_session.row_version,
            started_at=interview_session.started_at,
            completed_at=interview_session.completed_at,
            degraded_modes=list(interview_session.degraded_modes),
            created_at=interview_session.created_at,
        )

    @staticmethod
    def _session(row: InterviewSessionRow) -> InterviewSession:
        return InterviewSession(
            interview_session_id=OpaqueId(row.interview_session_id),
            scope=ApplicantScope(row.company_id, row.applicant_id, row.invitation_id),
            interview_strategy_id=OpaqueId(row.interview_strategy_id),
            competency_model_version_id=OpaqueId(row.competency_model_version_id),
            state=SessionState(row.state),
            session_sequence=row.session_sequence,
            row_version=row.row_version,
            started_at=_instant(row.started_at),
            completed_at=_instant(row.completed_at),
            degraded_modes=tuple(row.degraded_modes),
            created_at=_required_instant(row.created_at),
        )

    @staticmethod
    def _turn_row(turn: Turn) -> TurnRow:
        return TurnRow(
            turn_id=str(turn.turn_id),
            company_id=str(turn.company_id),
            interview_session_id=str(turn.interview_session_id),
            sequence=turn.sequence,
            speaker=turn.speaker.value,
            status=turn.status.value,
            text=turn.text.reveal() if turn.text is not None else None,
            target_criterion_id=(
                str(turn.target_criterion_id) if turn.target_criterion_id is not None else None
            ),
            idempotency_key=turn.idempotency_key,
            model_config_version=turn.model_config_version,
            finalized_at=turn.finalized_at,
            created_at=turn.created_at,
        )

    @staticmethod
    def _turn(row: TurnRow) -> Turn:
        return Turn(
            turn_id=OpaqueId(row.turn_id),
            company_id=OpaqueId(row.company_id),
            interview_session_id=OpaqueId(row.interview_session_id),
            sequence=row.sequence,
            speaker=TurnSpeaker(row.speaker),
            status=TurnStatus(row.status),
            text=ProtectedText(row.text) if row.text is not None else None,
            target_criterion_id=(
                OpaqueId(row.target_criterion_id) if row.target_criterion_id is not None else None
            ),
            idempotency_key=row.idempotency_key,
            model_config_version=row.model_config_version,
            finalized_at=_instant(row.finalized_at),
            created_at=_required_instant(row.created_at),
        )

    @staticmethod
    def _checkpoint_row(checkpoint: SessionCheckpoint) -> SessionCheckpointRow:
        return SessionCheckpointRow(
            checkpoint_id=str(checkpoint.checkpoint_id),
            company_id=str(checkpoint.company_id),
            interview_session_id=str(checkpoint.interview_session_id),
            session_sequence=checkpoint.session_sequence,
            last_final_turn_id=(
                str(checkpoint.last_final_turn_id)
                if checkpoint.last_final_turn_id is not None
                else None
            ),
            last_media_chunk_sequence=checkpoint.last_media_chunk_sequence,
            pending_turn_id=(
                str(checkpoint.pending_turn_id) if checkpoint.pending_turn_id is not None else None
            ),
            hot_view_sync_status=checkpoint.hot_view_sync_status.value,
            created_at=checkpoint.created_at,
        )

    @staticmethod
    def _checkpoint(row: SessionCheckpointRow) -> SessionCheckpoint:
        return SessionCheckpoint(
            checkpoint_id=OpaqueId(row.checkpoint_id),
            company_id=OpaqueId(row.company_id),
            interview_session_id=OpaqueId(row.interview_session_id),
            session_sequence=row.session_sequence,
            last_final_turn_id=(
                OpaqueId(row.last_final_turn_id) if row.last_final_turn_id is not None else None
            ),
            last_media_chunk_sequence=row.last_media_chunk_sequence,
            pending_turn_id=(
                OpaqueId(row.pending_turn_id) if row.pending_turn_id is not None else None
            ),
            hot_view_sync_status=HotViewSyncStatus(row.hot_view_sync_status),
            created_at=_required_instant(row.created_at),
        )

    @staticmethod
    def _chunk_row(chunk: RecordingChunk) -> RecordingChunkRow:
        return RecordingChunkRow(
            recording_chunk_id=str(chunk.recording_chunk_id),
            company_id=str(chunk.company_id),
            interview_session_id=str(chunk.interview_session_id),
            sequence=chunk.sequence,
            object_key=chunk.object_key,
            content_hash=chunk.content_hash,
            byte_size=chunk.byte_size,
            session_start_ms=chunk.session_start_ms,
            session_end_ms=chunk.session_end_ms,
            upload_status=chunk.upload_status.value,
            idempotency_key=chunk.idempotency_key,
            created_at=chunk.created_at,
        )

    @staticmethod
    def _chunk(row: RecordingChunkRow) -> RecordingChunk:
        return RecordingChunk(
            recording_chunk_id=OpaqueId(row.recording_chunk_id),
            company_id=OpaqueId(row.company_id),
            interview_session_id=OpaqueId(row.interview_session_id),
            sequence=row.sequence,
            object_key=row.object_key,
            content_hash=row.content_hash,
            byte_size=row.byte_size,
            session_start_ms=row.session_start_ms,
            session_end_ms=row.session_end_ms,
            upload_status=UploadStatus(row.upload_status),
            idempotency_key=row.idempotency_key,
            created_at=_required_instant(row.created_at),
        )


def _instant(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _required_instant(value: datetime) -> datetime:
    result = _instant(value)
    if result is None:
        raise ValueError("stored timestamp is required")
    return result
