from __future__ import annotations

from pathlib import Path

import pytest
from interview_evidence.reporting.application.review_service import ReviewService
from interview_evidence.shared.tenant import ActorType, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_tenant_context,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SOURCE = REPOSITORY_ROOT / "backend" / "src" / "interview_evidence"
FINAL_DECISION_FILES = {
    BACKEND_SOURCE / "reporting" / "domain" / "review.py",
    BACKEND_SOURCE / "reporting" / "application" / "review_service.py",
    BACKEND_SOURCE / "reporting" / "api" / "company_routes.py",
}


def test_only_human_reporting_paths_can_create_a_final_decision() -> None:
    matches = {
        path
        for path in BACKEND_SOURCE.rglob("*.py")
        if "final_decision" in path.read_text(encoding="utf-8")
    }
    assert matches == FINAL_DECISION_FILES

    company_context = TenantContext(**make_tenant_context())
    applicant_context = TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.APPLICANT,
        actor_id=APPLICANT_ID,
        request_id="018f2000-0000-7000-8000-000000000910",
        trace_id="human-control-applicant",
    )
    system_context = TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.SYSTEM,
        actor_id="018f2000-0000-7000-8000-000000000911",
        request_id="018f2000-0000-7000-8000-000000000912",
        trace_id="human-control-system",
    )
    service = ReviewService()

    for context in (applicant_context, system_context):
        with pytest.raises(PermissionError):
            service.final_decision(
                context,
                invitation_id=INVITATION_ID,
                decision="advance",
                reason="금지된 자동 결정",
                idempotency_key=f"human-control-{context.actor_type.value}-0001",
            )

    decision = service.final_decision(
        company_context,
        invitation_id=INVITATION_ID,
        decision="hold",
        reason="회사 담당자 추가 검토",
        idempotency_key="human-control-company-0001",
    )
    assert decision.company_user_id == company_context.actor_id


def test_no_runtime_source_defines_nonverbal_competency_scoring() -> None:
    forbidden = {
        "nonverbal_score",
        "facial_expression_score",
        "emotion_score",
        "gaze_score",
        "eye_contact_score",
    }
    source = "\n".join(
        path.read_text(encoding="utf-8").casefold() for path in BACKEND_SOURCE.rglob("*.py")
    )

    assert not any(term in source for term in forbidden)
