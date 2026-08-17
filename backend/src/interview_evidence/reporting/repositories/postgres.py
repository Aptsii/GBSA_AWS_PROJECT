from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from interview_evidence.shared.database import Base
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


class TranscriptSegmentRow(Base):
    __tablename__ = "transcript_segments"
    transcript_segment_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    turn_id: Mapped[str] = mapped_column(String(36), nullable=False)
    speaker: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    session_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    session_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    source_audio_key: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    corrected_by: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RecordingAssetRow(Base):
    __tablename__ = "recording_assets"
    recording_asset_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    missing_ranges: Mapped[list[list[int]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SessionEventRow(Base):
    __tablename__ = "reporting_session_events"
    session_event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    session_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    session_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    technical_failure: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReportRow(Base):
    __tablename__ = "reports"
    report_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    interview_session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competency_model_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    report_version: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    model_config_version: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReportItemRow(Base):
    __tablename__ = "report_items"
    report_item_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    report_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    criterion_id: Mapped[str] = mapped_column(String(36), nullable=False)
    competency_model_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assessment_state: Mapped[str] = mapped_column(String(32), nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    uncertainty: Mapped[str] = mapped_column(Text, nullable=False)
    follow_up_question: Mapped[str | None] = mapped_column(Text)


class EvidenceRow(Base):
    __tablename__ = "evidence"
    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    report_item_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    criterion_id: Mapped[str] = mapped_column(String(36), nullable=False)
    competency_model_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    answer_turn_id: Mapped[str] = mapped_column(String(36), nullable=False)
    transcript_segment_id: Mapped[str] = mapped_column(String(36), nullable=False)
    video_start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    video_end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    observation: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    sufficiency: Mapped[str] = mapped_column(String(32), nullable=False)
    generation_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class HumanReviewRow(Base):
    __tablename__ = "human_reviews"
    human_review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    report_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    company_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    review_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    value: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeletionRequestRow(Base):
    __tablename__ = "deletion_requests"
    deletion_request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False)
    invitation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    policy_snapshot: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DeletionManifestRow(Base):
    __tablename__ = "deletion_manifests"
    manifest_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    deletion_request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    manifest_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class DeletionTargetRow(Base):
    __tablename__ = "deletion_targets"
    target_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    manifest_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    store: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_lane: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(128))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def report_row(self, context: TenantContext, report_id: str | OpaqueId) -> ReportRow:
        row = self.session.get(ReportRow, str(OpaqueId(report_id)))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        ensure_company_scope(context, row.company_id)
        return row

    def report_items(
        self, context: TenantContext, report_id: str | OpaqueId
    ) -> tuple[ReportItemRow, ...]:
        self.report_row(context, report_id)
        rows = self.session.scalars(
            select(ReportItemRow)
            .where(
                ReportItemRow.company_id == str(context.company_id),
                ReportItemRow.report_id == str(OpaqueId(report_id)),
            )
            .order_by(ReportItemRow.criterion_id, ReportItemRow.report_item_id)
        ).all()
        return tuple(rows)

    def transcript_rows(
        self, context: TenantContext, session_id: str | OpaqueId
    ) -> tuple[TranscriptSegmentRow, ...]:
        ensure_company_scope(context, context.company_id)
        rows = self.session.scalars(
            select(TranscriptSegmentRow)
            .where(
                TranscriptSegmentRow.company_id == str(context.company_id),
                TranscriptSegmentRow.interview_session_id == str(OpaqueId(session_id)),
            )
            .order_by(
                TranscriptSegmentRow.session_start_ms,
                TranscriptSegmentRow.transcript_segment_id,
            )
        ).all()
        return tuple(rows)

    def recording_asset_rows(
        self, context: TenantContext, session_id: str | OpaqueId
    ) -> tuple[RecordingAssetRow, ...]:
        ensure_company_scope(context, context.company_id)
        rows = self.session.scalars(
            select(RecordingAssetRow)
            .where(
                RecordingAssetRow.company_id == str(context.company_id),
                RecordingAssetRow.interview_session_id == str(OpaqueId(session_id)),
            )
            .order_by(RecordingAssetRow.created_at, RecordingAssetRow.recording_asset_id)
        ).all()
        return tuple(rows)

    def session_event_rows(
        self, context: TenantContext, session_id: str | OpaqueId
    ) -> tuple[SessionEventRow, ...]:
        ensure_company_scope(context, context.company_id)
        rows = self.session.scalars(
            select(SessionEventRow)
            .where(
                SessionEventRow.company_id == str(context.company_id),
                SessionEventRow.interview_session_id == str(OpaqueId(session_id)),
            )
            .order_by(SessionEventRow.session_start_ms, SessionEventRow.session_event_id)
        ).all()
        return tuple(rows)

    def evidence_rows(
        self, context: TenantContext, report_item_id: str | OpaqueId
    ) -> tuple[EvidenceRow, ...]:
        ensure_company_scope(context, context.company_id)
        rows = self.session.scalars(
            select(EvidenceRow)
            .where(
                EvidenceRow.company_id == str(context.company_id),
                EvidenceRow.report_item_id == str(OpaqueId(report_item_id)),
            )
            .order_by(EvidenceRow.video_start_ms, EvidenceRow.evidence_id)
        ).all()
        return tuple(rows)

    def human_review_rows(
        self, context: TenantContext, report_id: str | OpaqueId
    ) -> tuple[HumanReviewRow, ...]:
        self.report_row(context, report_id)
        rows = self.session.scalars(
            select(HumanReviewRow)
            .where(
                HumanReviewRow.company_id == str(context.company_id),
                HumanReviewRow.report_id == str(OpaqueId(report_id)),
            )
            .order_by(HumanReviewRow.created_at, HumanReviewRow.human_review_id)
        ).all()
        return tuple(rows)

    def deletion_request_row(
        self, context: TenantContext, deletion_request_id: str | OpaqueId
    ) -> DeletionRequestRow:
        row = self.session.get(DeletionRequestRow, str(OpaqueId(deletion_request_id)))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        ensure_company_scope(context, row.company_id)
        return row

    def deletion_manifest_row(
        self, context: TenantContext, deletion_request_id: str | OpaqueId
    ) -> DeletionManifestRow:
        self.deletion_request_row(context, deletion_request_id)
        row = self.session.scalar(
            select(DeletionManifestRow).where(
                DeletionManifestRow.company_id == str(context.company_id),
                DeletionManifestRow.deletion_request_id == str(OpaqueId(deletion_request_id)),
            )
        )
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        return row

    def deletion_target_rows(
        self, context: TenantContext, manifest_id: str | OpaqueId
    ) -> tuple[DeletionTargetRow, ...]:
        checked_manifest_id = str(OpaqueId(manifest_id))
        manifest = self.session.get(DeletionManifestRow, checked_manifest_id)
        if manifest is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        ensure_company_scope(context, manifest.company_id)
        rows = self.session.scalars(
            select(DeletionTargetRow)
            .where(
                DeletionTargetRow.company_id == str(context.company_id),
                DeletionTargetRow.manifest_id == checked_manifest_id,
            )
            .order_by(DeletionTargetRow.target_id)
        ).all()
        return tuple(rows)

    def add(self, context: TenantContext, row: Base) -> None:
        company_id = getattr(row, "company_id", None)
        if not isinstance(company_id, str):
            raise ValueError("reporting rows require company_id")
        ensure_company_scope(context, company_id)
        self.session.add(row)
        self.session.flush()
