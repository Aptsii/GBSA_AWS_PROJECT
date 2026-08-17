from __future__ import annotations

from collections.abc import Callable

from fastapi import Request
from sqlalchemy.orm import Session

from interview_evidence.shared.aws_clients.ports import ObjectStoragePort
from interview_evidence.shared.ids import Clock, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.api.applicant_routes import ApplicantRouteRuntime
from interview_evidence.submission_analysis.application.authorization import (
    CompanyAuthorizationContracts,
    SubmissionAuthorizationGate,
)
from interview_evidence.submission_analysis.application.submission_service import (
    SubmissionApplicationService,
)
from interview_evidence.submission_analysis.application.submission_validator import (
    SubmissionValidator,
)
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)


def create_submission_runtime(
    session: Session,
    *,
    authorization_contracts: CompanyAuthorizationContracts,
    object_storage: ObjectStoragePort,
    scope_provider: Callable[[Request], tuple[TenantContext, ApplicantScope]],
    clock: Clock | None = None,
) -> ApplicantRouteRuntime:
    active_clock = clock or SystemClock()
    id_generator = UUID7Generator(active_clock)
    repository = SubmissionAnalysisRepository(session)
    service = SubmissionApplicationService(
        repository=repository,
        authorization=SubmissionAuthorizationGate(authorization_contracts),
        object_storage=SubmissionObjectStorage(
            object_storage,
            clock=active_clock,
            id_generator=id_generator,
        ),
        validator=SubmissionValidator(),
        clock=active_clock,
        id_generator=id_generator,
    )
    return ApplicantRouteRuntime(service=service, scope_provider=scope_provider)
