from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interview_evidence.company_management.domain.criteria import (
    CompetencyModelVersion,
    EvaluationCriterion,
)
from interview_evidence.company_management.domain.hiring import Campaign
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000001")
POSITION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000002")
VERSION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000003")
OTHER_VERSION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000004")
CRITERION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000005")
CAMPAIGN_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000006")


def _criterion() -> EvaluationCriterion:
    return EvaluationCriterion(
        criterion_id=CRITERION_ID,
        company_id=COMPANY_ID,
        competency_model_version_id=VERSION_ID,
        code="BACKEND_DESIGN",
        name="백엔드 설계",
        description="경계와 트레이드오프를 설명한다.",
        weight=1.0,
        good_evidence={"signals": ["tradeoff"]},
        weak_evidence={"signals": ["generic"]},
        abstain_guidance="답변 근거가 부족하면 판단을 유보한다.",
        common_questions=("최근 설계 결정을 설명해 주세요.",),
        required=True,
    )


def test_published_criterion_version_is_immutable() -> None:
    draft = CompetencyModelVersion(
        competency_model_version_id=VERSION_ID,
        company_id=COMPANY_ID,
        position_id=POSITION_ID,
        version_number=1,
        criteria=(_criterion(),),
        prohibited_topics=("가족관계",),
        interview_duration_minutes=40,
        persona_definition={"name": "하루", "tone": "professional"},
    )

    published = draft.publish(NOW)

    assert published.status.value == "published"
    assert published.published_at == NOW
    with pytest.raises(SafeApplicationError) as error:
        published.replace_criteria((_criterion(),))
    assert error.value.code is ErrorCode.CONFLICT


def test_campaign_version_pin_cannot_change_after_first_invitation() -> None:
    campaign = Campaign(
        campaign_id=CAMPAIGN_ID,
        company_id=COMPANY_ID,
        position_id=POSITION_ID,
        competency_model_version_id=VERSION_ID,
        name="2026 백엔드 채용",
        candidate_instructions="안내를 확인해 주세요.",
    ).publish(NOW)

    pinned = campaign.mark_invitation_issued()

    with pytest.raises(SafeApplicationError) as error:
        pinned.pin_competency_model_version(OTHER_VERSION_ID)
    assert error.value.code is ErrorCode.CONFLICT
