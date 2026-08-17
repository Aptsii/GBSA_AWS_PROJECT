from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.reporting.domain.deletion import (
    DeletionManifest,
    DeletionRequest,
    DeletionTarget,
)
from interview_evidence.shared.ids import OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class DeletionService:
    def __init__(self) -> None:
        self._ids = UUID7Generator()

    def request(
        self, context: TenantContext, scope: ApplicantScope, *, reason: str
    ) -> DeletionRequest:
        ensure_applicant_scope(context, scope)
        return DeletionRequest(self._ids.new(), scope, reason, datetime.now(UTC), {"version": 1})

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
