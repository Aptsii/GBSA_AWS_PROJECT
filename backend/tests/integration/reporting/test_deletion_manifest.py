from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.reporting.application.deletion_service import DeletionService
from interview_evidence.shared.messaging.outbox import AggregateRef, OutboxEvent
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_tenant_context,
)


def test_deletion_manifest_retries_and_completes_only_after_verified_absence() -> None:
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    service = DeletionService()
    request = service.request(context, scope, reason="지원자 요청")
    manifest = service.enumerate(
        request,
        (
            ("aurora", "report", "018f2000-0000-7000-8000-000000000240"),
            ("s3", "video", "018f2000-0000-7000-8000-000000000254"),
        ),
    )
    service.record_result(manifest, manifest.targets[0].target_id, verified_absent=True)
    service.record_result(manifest, manifest.targets[1].target_id, verified_absent=False)
    assert manifest.status == "partially_completed"
    service.record_result(manifest, manifest.targets[1].target_id, verified_absent=True)
    assert manifest.status == "completed"


def test_retention_expired_event_starts_scoped_deletion_request() -> None:
    context = TenantContext(**make_tenant_context())
    service = DeletionService()
    policy_snapshot_id = "018f2000-0000-7000-8000-000000000270"
    event = OutboxEvent(
        event_id="018f2000-0000-7000-8000-000000000271",
        company_id=COMPANY_ID,
        event_type="retention.expired",
        event_version=1,
        aggregate=AggregateRef("invitation", INVITATION_ID, 1),
        idempotency_key="retention-expired-0001",
        occurred_at=datetime(2026, 8, 17, tzinfo=UTC),
        trace_id="trace-retention-0001",
        correlation_id="018f2000-0000-7000-8000-000000000272",
        causation_id=None,
        payload={
            "invitation_id": INVITATION_ID,
            "applicant_id": APPLICANT_ID,
            "policy_snapshot_id": policy_snapshot_id,
            "expired_at": "2026-08-17T00:00:00Z",
        },
    )

    request = service.consume_retention_expired(context, event)

    assert request.scope == ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    assert request.reason == "retention_expired"
    assert request.policy_snapshot["policy_snapshot_id"] == policy_snapshot_id
