from __future__ import annotations

from interview_evidence.reporting.application.deletion_service import DeletionService
from interview_evidence.reporting.domain.deletion import DeletionStatus
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_tenant_context,
)


def test_deletion_retries_and_completes_only_after_every_store_is_absent() -> None:
    context = TenantContext(**make_tenant_context())
    service = DeletionService()
    request = service.request(
        context,
        ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID),
        reason="지원자 삭제 요청",
    )
    manifest = service.enumerate(
        request,
        (
            ("aurora", "relational_rows", "018f2000-0000-7000-8000-000000000801"),
            ("dynamodb", "session_hot_view", "018f2000-0000-7000-8000-000000000802"),
            ("s3", "applicant_objects", "018f2000-0000-7000-8000-000000000803"),
            ("opensearch", "search_documents", "018f2000-0000-7000-8000-000000000804"),
        ),
    )

    search_target = manifest.targets[-1]
    service.record_result(
        manifest,
        search_target.target_id,
        verified_absent=False,
        error_code="TEMPORARY_STORE_UNAVAILABLE",
    )
    assert manifest.status is DeletionStatus.RETRYING
    assert search_target.attempts == 1
    assert search_target.last_error_code == "TEMPORARY_STORE_UNAVAILABLE"

    for target in manifest.targets[:-1]:
        service.record_result(manifest, target.target_id, verified_absent=True)
    assert manifest.status is DeletionStatus.PARTIALLY_COMPLETED
    assert manifest.status is not DeletionStatus.COMPLETED

    service.record_result(manifest, search_target.target_id, verified_absent=True)

    assert manifest.status is DeletionStatus.COMPLETED
    assert all(target.status == "verified_absent" for target in manifest.targets)
    assert search_target.attempts == 2
    assert search_target.last_error_code is None
