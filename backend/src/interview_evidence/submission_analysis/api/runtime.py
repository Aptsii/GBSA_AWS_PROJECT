from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Request
from sqlalchemy.orm import Session

from interview_evidence.shared.aws_clients.ports import ObjectStoragePort
from interview_evidence.shared.ids import Clock, SystemClock, UUID7Generator
from interview_evidence.shared.persistence import SQLAlchemyOutbox
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.adapters.search import InMemorySubmissionSearch
from interview_evidence.submission_analysis.api.applicant_routes import ApplicantRouteRuntime
from interview_evidence.submission_analysis.application.analysis_pipeline import (
    CompanyCriterionSnapshotProvider,
    SubmissionAnalysisCoordinator,
)
from interview_evidence.submission_analysis.application.authorization import (
    CompanyAuthorizationContracts,
    SubmissionAuthorizationGate,
)
from interview_evidence.submission_analysis.application.deletion_targets import (
    SubmissionDeletionService,
)
from interview_evidence.submission_analysis.application.retrieval import HybridRetriever
from interview_evidence.submission_analysis.application.submission_service import (
    SubmissionApplicationService,
)
from interview_evidence.submission_analysis.application.submission_validator import (
    SubmissionValidator,
)
from interview_evidence.submission_analysis.contracts import SubmissionAnalysisPublicService
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)


@dataclass(frozen=True, slots=True)
class SubmissionRuntimeBundle:
    applicant: ApplicantRouteRuntime
    public: SubmissionAnalysisPublicService


def create_submission_runtime(
    session: Session,
    *,
    authorization_contracts: CompanyAuthorizationContracts,
    object_storage: ObjectStoragePort,
    scope_provider: Callable[[Request], tuple[TenantContext, ApplicantScope]],
    clock: Clock | None = None,
) -> ApplicantRouteRuntime:
    return create_submission_runtimes(
        session,
        authorization_contracts=authorization_contracts,
        object_storage=object_storage,
        scope_provider=scope_provider,
        clock=clock,
    ).applicant


def create_submission_runtimes(
    session: Session,
    *,
    authorization_contracts: CompanyAuthorizationContracts,
    object_storage: ObjectStoragePort,
    scope_provider: Callable[[Request], tuple[TenantContext, ApplicantScope]],
    clock: Clock | None = None,
) -> SubmissionRuntimeBundle:
    active_clock = clock or SystemClock()
    id_generator = UUID7Generator(active_clock)
    repository = SubmissionAnalysisRepository(session)
    submission_storage = SubmissionObjectStorage(
        object_storage,
        clock=active_clock,
        id_generator=id_generator,
    )
    search = InMemorySubmissionSearch()
    coordinator = SubmissionAnalysisCoordinator(
        repository=repository,
        object_storage=submission_storage,
        criterion_snapshot_provider=CompanyCriterionSnapshotProvider(
            authorization_contracts
        ),
        outbox=SQLAlchemyOutbox(session),
        clock=active_clock,
        id_generator=id_generator,
    )
    service = SubmissionApplicationService(
        repository=repository,
        authorization=SubmissionAuthorizationGate(authorization_contracts),
        object_storage=submission_storage,
        validator=SubmissionValidator(),
        clock=active_clock,
        id_generator=id_generator,
        analysis_dispatcher=coordinator,
    )
    return SubmissionRuntimeBundle(
        applicant=ApplicantRouteRuntime(service=service, scope_provider=scope_provider),
        public=SubmissionAnalysisPublicService(
            repository=repository,
            retriever=HybridRetriever(search),
            deletion=SubmissionDeletionService(repository, submission_storage, search),
        ),
    )
