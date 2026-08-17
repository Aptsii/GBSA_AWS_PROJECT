from __future__ import annotations

import pytest
from interview_evidence.interview_engine.application.question_policy import QuestionPolicy


def test_policy_rejects_forbidden_duplicate_multi_question_and_axis_change() -> None:
    policy = QuestionPolicy(prohibited_topics=("가족",))
    policy.validate(
        "기술 선택 이유를 설명해 주세요.", criterion_id="criterion-1", previous_questions=()
    )
    for question in ("가족 관계는?", "첫 질문? 두 번째 질문?", "기술 선택 이유를 설명해 주세요."):
        with pytest.raises(ValueError):
            policy.validate(
                question,
                criterion_id="criterion-1",
                previous_questions=("기술 선택 이유를 설명해 주세요.",),
            )
    with pytest.raises(ValueError, match="criterion"):
        policy.validate(
            "다른 경험을 설명해 주세요.",
            criterion_id="criterion-2",
            expected_criterion_id="criterion-1",
            previous_questions=(),
        )
