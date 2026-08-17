from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interview_evidence.reporting.adapters.playback import PlaybackLocator
from interview_evidence.reporting.api.runtime import SQLAlchemyReportingRouteService
from interview_evidence.reporting.repositories.postgres import (
    DeletionManifestRow,
    DeletionRequestRow,
    DeletionTargetRow,
    EvidenceRow,
    HumanReviewRow,
    ReportingRepository,
    ReportItemRow,
    ReportRow,
    TranscriptSegmentRow,
)
from interview_evidence.shared.database import Base
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import TenantContext, TenantScopeViolation
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    CRITERION_ID,
    INVITATION_ID,
    MODEL_ID,
    OTHER_COMPANY_ID,
    REPORT_ID,
    SESSION_ID,
    USER_ID,
    make_other_tenant_context,
    make_tenant_context,
)

NOW = datetime(2026, 8, 17, tzinfo=UTC)
REPORT_ITEM_ID = "018f2000-0000-7000-8000-000000000251"
SEGMENT_ID = "018f2000-0000-7000-8000-000000000252"
EVIDENCE_ID = "018f2000-0000-7000-8000-000000000253"
REVIEW_ID = "018f2000-0000-7000-8000-000000000254"
DELETION_REQUEST_ID = "018f2000-0000-7000-8000-000000000260"
MANIFEST_ID = "018f2000-0000-7000-8000-000000000261"
TARGET_ID = "018f2000-0000-7000-8000-000000000262"
OTHER_INVITATION_ID = "018f2000-0000-7000-8000-000000000263"


def test_cross_tenant_media_locator_is_denied() -> None:
    with pytest.raises(TenantScopeViolation):
        PlaybackLocator().issue(
            TenantContext(**make_other_tenant_context()),
            company_id=COMPANY_ID,
            recording_asset_id="018f2000-0000-7000-8000-000000000254",
        )
    assert COMPANY_ID != OTHER_COMPANY_ID


def test_reporting_repository_scopes_timeline_evidence_review_and_deletion_reads() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            repository = ReportingRepository(session)
            context = TenantContext(**make_tenant_context())
            other_context = TenantContext(**make_other_tenant_context())
            repository.add(
                context,
                ReportRow(
                    report_id=REPORT_ID,
                    company_id=COMPANY_ID,
                    interview_session_id=SESSION_ID,
                    competency_model_version_id=MODEL_ID,
                    report_version=1,
                    kind="ai_original",
                    status="ready",
                    summary="summary",
                    model_config_version="report-v1",
                    prompt_version="prompt-v1",
                    created_at=NOW,
                ),
            )
            repository.add(
                context,
                ReportItemRow(
                    report_item_id=REPORT_ITEM_ID,
                    company_id=COMPANY_ID,
                    report_id=REPORT_ID,
                    criterion_id=CRITERION_ID,
                    competency_model_version_id=MODEL_ID,
                    assessment_state="confirmed",
                    observation="관찰",
                    rationale="근거",
                    uncertainty="없음",
                    follow_up_question=None,
                ),
            )
            repository.add(
                context,
                TranscriptSegmentRow(
                    transcript_segment_id=SEGMENT_ID,
                    company_id=COMPANY_ID,
                    interview_session_id=SESSION_ID,
                    turn_id="018f2000-0000-7000-8000-000000000231",
                    speaker="applicant",
                    text="protected",
                    confidence=0.95,
                    session_start_ms=100,
                    session_end_ms=900,
                    source_audio_key="reporting/audio",
                    version=1,
                    corrected_by=None,
                    created_at=NOW,
                ),
            )
            repository.add(
                context,
                EvidenceRow(
                    evidence_id=EVIDENCE_ID,
                    company_id=COMPANY_ID,
                    report_item_id=REPORT_ITEM_ID,
                    criterion_id=CRITERION_ID,
                    competency_model_version_id=MODEL_ID,
                    answer_turn_id="018f2000-0000-7000-8000-000000000231",
                    transcript_segment_id=SEGMENT_ID,
                    video_start_ms=100,
                    video_end_ms=900,
                    observation="실제 답변 관찰",
                    rationale="실제 답변 근거",
                    sufficiency="direct",
                    generation_version="report-v1",
                    created_at=NOW,
                ),
            )
            repository.add(
                context,
                HumanReviewRow(
                    human_review_id=REVIEW_ID,
                    company_id=COMPANY_ID,
                    report_id=REPORT_ID,
                    company_user_id=USER_ID,
                    review_type="bookmark",
                    target_id=REPORT_ITEM_ID,
                    value={"label_code": "follow_up"},
                    reason=None,
                    idempotency_key="tenant-review-0001",
                    created_at=NOW,
                ),
            )
            repository.add(
                context,
                DeletionRequestRow(
                    deletion_request_id=DELETION_REQUEST_ID,
                    company_id=COMPANY_ID,
                    applicant_id=APPLICANT_ID,
                    invitation_id=INVITATION_ID,
                    reason="retention_expired",
                    policy_snapshot={"version": 1},
                    status="requested",
                    requested_at=NOW,
                ),
            )
            repository.add(
                context,
                DeletionManifestRow(
                    manifest_id=MANIFEST_ID,
                    company_id=COMPANY_ID,
                    deletion_request_id=DELETION_REQUEST_ID,
                    manifest_version=1,
                    status="deleting",
                ),
            )
            repository.add(
                context,
                DeletionTargetRow(
                    target_id=TARGET_ID,
                    company_id=COMPANY_ID,
                    manifest_id=MANIFEST_ID,
                    store="s3",
                    target_type="recording",
                    owner_lane="D",
                    status="pending",
                    attempts=0,
                    last_error_code=None,
                    verified_at=None,
                ),
            )

            assert repository.report_items(context, REPORT_ID)[0].report_item_id == REPORT_ITEM_ID
            assert (
                repository.transcript_rows(context, SESSION_ID)[0].transcript_segment_id
                == SEGMENT_ID
            )
            assert repository.evidence_rows(context, REPORT_ITEM_ID)[0].evidence_id == EVIDENCE_ID
            assert repository.human_review_rows(context, REPORT_ID)[0].human_review_id == REVIEW_ID
            assert (
                repository.deletion_request_row(context, DELETION_REQUEST_ID).company_id
                == COMPANY_ID
            )
            assert (
                repository.deletion_manifest_row(context, DELETION_REQUEST_ID).manifest_id
                == MANIFEST_ID
            )
            assert repository.deletion_target_rows(context, MANIFEST_ID)[0].target_id == TARGET_ID
            with pytest.raises(TenantScopeViolation):
                repository.report_row(other_context, REPORT_ID)
            with pytest.raises(TenantScopeViolation):
                repository.deletion_request_row(other_context, DELETION_REQUEST_ID)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_human_review_idempotency_key_is_scoped_per_company() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            ids = UUID7Generator(FixedClock(NOW))
            service = SQLAlchemyReportingRouteService(
                session,
                clock=FixedClock(NOW),
                id_generator=ids,
            )
            first = service.final_decision(
                context=TenantContext(**make_tenant_context()),
                invitation_id=INVITATION_ID,
                decision="hold",
                reason="첫 번째 기업의 사람 검토",
                idempotency_key="shared-final-decision-key-0001",
            )
            second = service.final_decision(
                context=TenantContext(**make_other_tenant_context()),
                invitation_id=OTHER_INVITATION_ID,
                decision="advance",
                reason="두 번째 기업의 사람 검토",
                idempotency_key="shared-final-decision-key-0001",
            )

            assert first["human_review_id"] != second["human_review_id"]
            assert session.query(HumanReviewRow).count() == 2
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
