from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from interview_evidence.reporting.api.company_routes import (
    DeletionRequestCreate,
    FinalDecisionCreate,
    HumanAssessmentReviewCreate,
    ReportingRouteRuntime,
    create_reporting_router,
)
from interview_evidence.shared.audit import AuditAppend
from interview_evidence.shared.tenant import TenantContext

from tests.fixtures.shared.factories import (
    INVITATION_ID,
    REPORT_ID,
    SESSION_ID,
    make_tenant_context,
)

REPORT_ITEM_ID = "018f2000-0000-7000-8000-000000000251"
HUMAN_REVIEW_ID = "018f2000-0000-7000-8000-000000000252"
DELETION_REQUEST_ID = "018f2000-0000-7000-8000-000000000260"


class _ReportingService:
    def get_report(self, **arguments: object) -> dict[str, object]:
        return {"report_id": REPORT_ID}

    def get_timeline(self, **arguments: object) -> dict[str, object]:
        return {"session_id": SESSION_ID, "entries": []}

    def create_review(self, **arguments: object) -> dict[str, object]:
        return {"human_review_id": HUMAN_REVIEW_ID}

    def create_artifact(self, **arguments: object) -> dict[str, object]:
        return {"human_review_id": HUMAN_REVIEW_ID}

    def final_decision(self, **arguments: object) -> dict[str, object]:
        return {"human_review_id": HUMAN_REVIEW_ID}

    def request_deletion(self, **arguments: object) -> dict[str, object]:
        return {"deletion_request_id": DELETION_REQUEST_ID}

    def deletion_status(self, **arguments: object) -> dict[str, object]:
        return {"deletion_request_id": DELETION_REQUEST_ID, "status": "requested"}


@dataclass
class _AuditAppender:
    commands: list[AuditAppend] = field(default_factory=list)

    async def append(self, context: TenantContext, command: AuditAppend) -> object:
        self.commands.append(command)
        return object()


def _client(audit_appender: _AuditAppender) -> TestClient:
    app = FastAPI()
    app.include_router(
        create_reporting_router(
            ReportingRouteRuntime(
                service=_ReportingService(),
                context_provider=lambda request: TenantContext(**make_tenant_context()),
                audit_appender=audit_appender,
            )
        ),
        prefix="/v1",
    )
    return TestClient(app)


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


def test_reporting_routes_emit_sanitized_protected_resource_audits() -> None:
    audit_appender = _AuditAppender()
    client = _client(audit_appender)
    idempotency_key = "reporting-contract-0001"

    responses = (
        client.get(f"/v1/interview-sessions/{SESSION_ID}/report"),
        client.get(f"/v1/interview-sessions/{SESSION_ID}/timeline?query=python"),
        client.post(
            f"/v1/reports/{REPORT_ID}/items/{REPORT_ITEM_ID}/reviews",
            headers={"Idempotency-Key": idempotency_key},
            json={"assessment_state": "needs_follow_up", "reason": "추가 확인 필요"},
        ),
        client.post(
            f"/v1/interview-sessions/{SESSION_ID}/review-artifacts",
            headers={"Idempotency-Key": idempotency_key},
            json={
                "review_type": "bookmark",
                "target_id": REPORT_ITEM_ID,
                "value": {"label_code": "follow_up"},
                "reason": "다시 검토",
            },
        ),
        client.post(
            f"/v1/invitations/{INVITATION_ID}/final-decisions",
            headers={"Idempotency-Key": idempotency_key},
            json={"decision": "hold", "reason": "사람 검토 대기"},
        ),
        client.post(
            "/v1/privacy/deletion-requests",
            headers={"Idempotency-Key": idempotency_key},
            json={"reason": "지원자 요청"},
        ),
        client.get(f"/v1/privacy/deletion-requests/{DELETION_REQUEST_ID}"),
    )

    assert [response.status_code for response in responses] == [200, 200, 201, 201, 201, 202, 200]
    assert [command.action for command in audit_appender.commands] == [
        "reporting.report_viewed",
        "reporting.timeline_viewed",
        "reporting.assessment_review_created",
        "reporting.review_artifact_created",
        "reporting.final_decision_recorded",
        "reporting.deletion_requested",
        "reporting.deletion_status_viewed",
    ]
    assert all("reason" not in command.metadata for command in audit_appender.commands)
