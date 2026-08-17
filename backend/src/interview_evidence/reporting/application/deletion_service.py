from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.reporting.domain.deletion import (
    DeletionManifest,
    DeletionRequest,
    DeletionTarget,
)
from interview_evidence.shared.ids import OpaqueId, UUID7Generator
from interview_evidence.shared.messaging.outbox import OutboxEvent
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class DeletionService:
    def __init__(self) -> None:
        self._ids = UUID7Generator()

    def request(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        *,
        reason: str,
        policy_snapshot: dict[str, object] | None = None,
    ) -> DeletionRequest:
        ensure_applicant_scope(context, scope)
        return DeletionRequest(
            self._ids.new(),
            scope,
            reason,
            datetime.now(UTC),
            policy_snapshot or {"version": 1},
        )

    def consume_retention_expired(
        self, context: TenantContext, event: OutboxEvent
    ) -> DeletionRequest:
        if event.event_type != "retention.expired" or event.event_version != 1:
            raise ValueError("unsupported retention event")
        if event.aggregate.aggregate_type != "invitation":
            raise ValueError("retention event aggregate must be an invitation")
        invitation_id = _payload_id(event, "invitation_id")
        applicant_id = _payload_id(event, "applicant_id")
        policy_snapshot_id = _payload_id(event, "policy_snapshot_id")
        if invitation_id != event.aggregate.aggregate_id:
            raise ValueError("retention event invitation does not match aggregate")
        scope = ApplicantScope(event.company_id, applicant_id, invitation_id)
        ensure_applicant_scope(context, scope)
        expired_at = event.payload.get("expired_at")
        if not isinstance(expired_at, str):
            raise ValueError("retention event is missing expired_at")
        return self.request(
            context,
            scope,
            reason="retention_expired",
            policy_snapshot={
                "version": event.event_version,
                "policy_snapshot_id": str(policy_snapshot_id),
                "expired_at": expired_at,
            },
        )

    def enumerate(
        self, request: DeletionRequest, raw_targets: tuple[tuple[str, str, str], ...]
    ) -> DeletionManifest:
        targets = [
            DeletionTarget(OpaqueId(target_id), store, target_type, "cross_lane")
            for store, target_type, target_id in raw_targets
        ]
        return DeletionManifest(self._ids.new(), request.deletion_request_id, targets)

    def record_result(
        self,
        manifest: DeletionManifest,
        target_id: str | OpaqueId,
        *,
        verified_absent: bool,
        error_code: str | None = None,
    ) -> None:
        checked = OpaqueId(target_id)
        target = next(item for item in manifest.targets if item.target_id == checked)
        target.attempts += 1
        target.status = "verified_absent" if verified_absent else "failed"
        target.last_error_code = None if verified_absent else (error_code or "DELETE_NOT_VERIFIED")
        target.verified_at = datetime.now(UTC) if verified_absent else None
        manifest.refresh()


def _payload_id(event: OutboxEvent, key: str) -> OpaqueId:
    value = event.payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"retention event is missing {key}")
    return OpaqueId(value)
