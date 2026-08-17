"""Durable-style checkpoint snapshots for reconnect recovery."""

from __future__ import annotations

from dataclasses import dataclass

from interview_evidence.interview_engine.domain.session import SessionState
from interview_evidence.interview_engine.domain.turn import HotViewSyncStatus, SessionCheckpoint
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(frozen=True, slots=True)
class ResumeSnapshot:
    interview_session_id: OpaqueId
    state: SessionState
    server_sequence: int
    last_final_turn_id: OpaqueId | None
    pending_turn_id: OpaqueId | None
    last_verified_recording_chunk_sequence: int
    degraded_modes: tuple[str, ...]
    stale_client: bool
    allowed_client_messages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _CheckpointRecord:
    checkpoint: SessionCheckpoint
    state: SessionState
    degraded_modes: tuple[str, ...]


class CheckpointService:
    __slots__ = ("_clock", "_id_generator", "_records")

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        id_generator: UUID7Generator | None = None,
    ) -> None:
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UUID7Generator(self._clock)
        self._records: dict[tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], _CheckpointRecord] = {}

    def record(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        session_sequence: int,
        last_final_turn_id: str | OpaqueId | None,
        last_media_chunk_sequence: int,
        pending_turn_id: str | OpaqueId | None = None,
        hot_view_sync_status: HotViewSyncStatus = HotViewSyncStatus.PENDING,
        state: SessionState = SessionState.PAUSED,
        degraded_modes: tuple[str, ...] = (),
    ) -> SessionCheckpoint:
        ensure_applicant_scope(context, scope)
        checked_session_id = OpaqueId(session_id)
        key = (*_scope_key(scope), checked_session_id)
        checkpoint = SessionCheckpoint(
            checkpoint_id=self._id_generator.new(),
            company_id=scope.company_id,
            interview_session_id=checked_session_id,
            session_sequence=session_sequence,
            last_final_turn_id=(
                OpaqueId(last_final_turn_id) if last_final_turn_id is not None else None
            ),
            last_media_chunk_sequence=last_media_chunk_sequence,
            pending_turn_id=OpaqueId(pending_turn_id) if pending_turn_id is not None else None,
            hot_view_sync_status=hot_view_sync_status,
            created_at=self._clock.now(),
        )
        existing = self._records.get(key)
        if existing is not None:
            if existing.checkpoint.session_sequence > session_sequence:
                raise ValueError("stale checkpoint sequence")
            if existing.checkpoint.session_sequence == session_sequence:
                comparable = (
                    existing.checkpoint.last_final_turn_id,
                    existing.checkpoint.last_media_chunk_sequence,
                    existing.checkpoint.pending_turn_id,
                    existing.state,
                    existing.degraded_modes,
                )
                requested = (
                    checkpoint.last_final_turn_id,
                    checkpoint.last_media_chunk_sequence,
                    checkpoint.pending_turn_id,
                    state,
                    degraded_modes,
                )
                if comparable != requested:
                    raise ValueError("checkpoint sequence already records different state")
                return existing.checkpoint
        self._records[key] = _CheckpointRecord(checkpoint, state, degraded_modes)
        return checkpoint

    def resume(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        client_sequence: int,
    ) -> ResumeSnapshot:
        ensure_applicant_scope(context, scope)
        checked_session_id = OpaqueId(session_id)
        record = self._records.get((*_scope_key(scope), checked_session_id))
        if record is None:
            raise LookupError("interview checkpoint was not found")
        checkpoint = record.checkpoint
        return ResumeSnapshot(
            interview_session_id=checked_session_id,
            state=record.state,
            server_sequence=checkpoint.session_sequence,
            last_final_turn_id=checkpoint.last_final_turn_id,
            pending_turn_id=checkpoint.pending_turn_id,
            last_verified_recording_chunk_sequence=checkpoint.last_media_chunk_sequence,
            degraded_modes=record.degraded_modes,
            stale_client=client_sequence < checkpoint.session_sequence,
            allowed_client_messages=("session.resume",)
            if record.state is SessionState.PAUSED
            else ("client.ack", "answer.complete", "audio.chunk.begin"),
        )


def _scope_key(scope: ApplicantScope) -> tuple[OpaqueId, OpaqueId, OpaqueId]:
    return scope.company_id, scope.applicant_id, scope.invitation_id
