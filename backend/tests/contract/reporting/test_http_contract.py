from __future__ import annotations

import pytest
from interview_evidence.reporting.api.company_routes import (
    DeletionRequestCreate,
    FinalDecisionCreate,
    HumanAssessmentReviewCreate,
)


def test_reporting_contract_models_reject_extra_fields() -> None:
    review = HumanAssessmentReviewCreate(
        assessment_state="needs_follow_up", reason="추가 확인이 필요합니다."
    )
    decision = FinalDecisionCreate(decision="hold", reason="사람 검토 대기")
    deletion = DeletionRequestCreate(reason="지원자 요청")
    assert review.assessment_state == "needs_follow_up"
    assert decision.decision == "hold"
    assert deletion.reason == "지원자 요청"
    with pytest.raises(ValueError):
        FinalDecisionCreate.model_validate(
            {"decision": "advance", "reason": "검토 완료", "ai_score": 0.9}
        )
