from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from interview_evidence.shared.aws_clients.ports import ObjectStoragePort
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, SystemClock, UUID7Generator
from interview_evidence.shared.persistence import SQLAlchemyOutbox
from interview_evidence.shared.tenant import TenantContext
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.application.analysis_pipeline import (
    CriterionSnapshotProvider,
    SubmissionAnalysisCoordinator,
)
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)


class AnalysisQueueEvent(Protocol):
    idempotency_key: str
    payload: Mapping[str, object]


CriterionProviderFactory = Callable[[Session], CriterionSnapshotProvider]


class UnavailableAnalysisQueueHandler:
    __slots__ = ()

    def handle_event(
        self,
        _context: TenantContext,
        _event: object,
    ) -> Mapping[str, object]:
        raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE)


class SubmissionAnalysisQueueHandler:
    __slots__ = (
        "_clock",
        "_criterion_provider_factory",
        "_object_storage",
        "_session_factory",
    )

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        object_storage: ObjectStoragePort,
        criterion_provider_factory: CriterionProviderFactory,
        clock: Clock | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._object_storage = object_storage
        self._criterion_provider_factory = criterion_provider_factory
        self._clock = clock or SystemClock()

    def handle_event(
        self,
        context: TenantContext,
        event: AnalysisQueueEvent,
    ) -> Mapping[str, object]:
        payload = event.payload
        submission_id = payload.get("submission_id")
        source_type = payload.get("source_type")
        analysis_version = payload.get("analysis_version")
        if not isinstance(submission_id, str) or not isinstance(source_type, str):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if analysis_version != 1:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        with self._session_factory() as session:
            repository = SubmissionAnalysisRepository(session)
            submission = repository.get_submission(context, submission_id)
            if submission.source_type.value != source_type:
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            ids = UUID7Generator(self._clock)
            coordinator = SubmissionAnalysisCoordinator(
                repository=repository,
                object_storage=SubmissionObjectStorage(
                    self._object_storage,
                    clock=self._clock,
                    id_generator=ids,
                ),
                criterion_snapshot_provider=self._criterion_provider_factory(session),
                outbox=SQLAlchemyOutbox(session),
                clock=self._clock,
                id_generator=ids,
            )
            completed = coordinator.execute(
                context,
                submission=submission,
                upload_id=None,
                idempotency_key=event.idempotency_key,
            )
            analysis = repository.latest_analysis(context, submission.submission_id)
            strategy = repository.latest_strategy(context, submission.scope)
            session.commit()
            return {
                "submission_id": str(completed.submission_id),
                "analysis_id": str(analysis.analysis_id) if analysis else None,
                "strategy_id": str(strategy.interview_strategy_id) if strategy else None,
                "status": completed.status.value,
                "impact_code": completed.failure_code,
            }
