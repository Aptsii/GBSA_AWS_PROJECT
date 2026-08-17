from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.reporting.application.deletion_service import DeletionService
from interview_evidence.reporting.application.review_service import ReviewService
from interview_evidence.reporting.domain.report import AssessmentState, Evidence, ReportItem
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    CRITERION_ID,
    INVITATION_ID,
    MODEL_ID,
    REPORT_ID,
    make_tenant_context,
)


def test_lane_d_quickstart_preserves_evidence_human_decision_and_deletion_gate() -> None:
    context = TenantContext(**make_tenant_context())
    evidence = Evidence(
        "018f2000-0000-7000-8000-000000000250",
        COMPANY_ID,
        "018f2000-0000-7000-8000-000000000251",
        CRITERION_ID,
        MODEL_ID,
        "018f2000-0000-7000-8000-000000000252",
        "018f2000-0000-7000-8000-000000000253",
        1000,
        3000,
        "복구 순서를 설명함",
        "최종 답변에서 직접 확인",
        "direct",
        "report-v1",
        datetime(2026, 8, 17, tzinfo=UTC),
    )
    item = ReportItem(
        evidence.report_item_id,
        REPORT_ID,
        CRITERION_ID,
        MODEL_ID,
        AssessmentState.CONFIRMED,
        "관찰",
        "근거",
        "낮음",
        (evidence,),
    )
    assert item.evidence == (evidence,)

    review = ReviewService().final_decision(
        context,
        invitation_id=INVITATION_ID,
        decision="hold",
        reason="담당자 추가 검토",
        idempotency_key="lane-d-final-decision-0001",
    )
    assert review.review_type == "final_decision"

    deletion = DeletionService()
    request = deletion.request(
        context,
        ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID),
        reason="지원자 요청",
    )
    manifest = deletion.enumerate(
        request,
        (("aurora", "report", REPORT_ID), ("s3", "video", evidence.evidence_id)),
    )
    deletion.record_result(manifest, manifest.targets[0].target_id, verified_absent=True)
    assert manifest.status != "completed"
    deletion.record_result(manifest, manifest.targets[1].target_id, verified_absent=True)
    assert manifest.status == "completed"
