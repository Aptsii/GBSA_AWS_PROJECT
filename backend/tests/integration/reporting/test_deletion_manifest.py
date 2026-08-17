from __future__ import annotations

from interview_evidence.reporting.application.deletion_service import DeletionService
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
