from __future__ import annotations

from interview_evidence.reporting.application.review_service import ReviewService
from interview_evidence.shared.tenant import TenantContext

from tests.fixtures.shared.factories import (
    INVITATION_ID,
    make_criterion_snapshot,
    make_invitation_snapshot,
    make_report_snapshot,
    make_session_snapshot,
    make_strategy_snapshot,
    make_tenant_context,
)


def test_company_to_human_decision_thin_journey_preserves_contract_axes() -> None:
    criterion = make_criterion_snapshot()
    invitation = make_invitation_snapshot()
    strategy = make_strategy_snapshot()
    session = make_session_snapshot()
    report = make_report_snapshot()

    company_ids = {
        criterion["company_id"],
        invitation["company_id"],
        strategy["company_id"],
        session["company_id"],
        report["company_id"],
    }
    model_ids = {
        criterion["competency_model_version_id"],
        strategy["competency_model_version_id"],
        session["competency_model_version_id"],
        report["competency_model_version_id"],
    }
    evidence = report["items"][0]["evidence"][0]
    source_candidate = strategy["source_reference_candidates"][0]

    assert company_ids == {criterion["company_id"]}
    assert model_ids == {criterion["competency_model_version_id"]}
    assert invitation["invitation_id"] == strategy["invitation_id"] == session["invitation_id"]
    assert source_candidate["source_type"] == "submission_chunk"
    assert evidence["evidence_type"] == "applicant_answer"
    assert evidence["answer_turn_speaker"] == "applicant"
    assert evidence["answer_turn_status"] == "final"
    assert evidence["technical_failure_overlap"] is False
    assert report["ai_original_immutable"] is True
    assert report["human_decision_status"] is None

    decision = ReviewService().final_decision(
        TenantContext(**make_tenant_context()),
        invitation_id=INVITATION_ID,
        decision="hold",
        reason="사람 면접에서 추가 확인",
        idempotency_key="e2e-human-decision-0001",
    )

    assert decision.review_type.value == "final_decision"
    assert decision.value == {"decision": "hold"}
    assert report["human_decision_status"] is None
