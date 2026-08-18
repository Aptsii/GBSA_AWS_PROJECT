from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime

from interview_evidence.shared.aws_clients.ports import FakeObjectStorage, ProtectedBytes
from interview_evidence.shared.database import Base
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.persistence import SQLAlchemyOutbox
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.application.analysis_pipeline import (
    SubmissionAnalysisCoordinator,
)
from interview_evidence.submission_analysis.application.authorization import (
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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_criterion_snapshot,
    make_tenant_context,
)
from tests.fixtures.shared.module_fakes import DeterministicModuleFakes


def _context() -> TenantContext:
    return TenantContext(**make_tenant_context())


def _scope() -> ApplicantScope:
    return ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)


def _criterion_snapshot(
    _context: TenantContext,
    _scope: ApplicantScope,
) -> Mapping[str, object]:
    return make_criterion_snapshot()


def _failing_criterion_snapshot(
    _context: TenantContext,
    _scope: ApplicantScope,
) -> Mapping[str, object]:
    raise SafeApplicationError(ErrorCode.INVALID_REQUEST)


def _service(
    session: Session,
    *,
    criterion_snapshot_provider=_criterion_snapshot,
) -> tuple[SubmissionApplicationService, SubmissionObjectStorage, SubmissionAnalysisRepository]:
    clock = FixedClock(datetime(2026, 8, 18, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x42" * size)
    repository = SubmissionAnalysisRepository(session)
    object_storage = SubmissionObjectStorage(FakeObjectStorage(), clock=clock, id_generator=ids)
    coordinator = SubmissionAnalysisCoordinator(
        repository=repository,
        object_storage=object_storage,
        criterion_snapshot_provider=criterion_snapshot_provider,
        outbox=SQLAlchemyOutbox(session),
        clock=clock,
        id_generator=ids,
    )
    return (
        SubmissionApplicationService(
            repository=repository,
            authorization=SubmissionAuthorizationGate(
                DeterministicModuleFakes(company_id=COMPANY_ID)
            ),
            object_storage=object_storage,
            validator=SubmissionValidator(max_file_bytes=2_000_000),
            clock=clock,
            id_generator=ids,
            analysis_dispatcher=coordinator,
        ),
        object_storage,
        repository,
    )


def _register_document(
    service: SubmissionApplicationService,
    object_storage: SubmissionObjectStorage,
    content: bytes,
    *,
    key_suffix: str,
) -> dict[str, object]:
    digest = hashlib.sha256(content).hexdigest()
    intent = service.create_upload_intent(
        context=_context(),
        scope=_scope(),
        idempotency_key=f"analysis-upload-{key_suffix}-0001",
        source_type="pdf",
        filename="portfolio.pdf",
        media_type="application/pdf",
        byte_size=len(content),
        sha256=digest,
    )
    object_storage.accept_upload(
        _context(),
        _scope(),
        upload_id=str(intent["upload_id"]),
        content=ProtectedBytes(content),
        media_type="application/pdf",
    )
    return service.register_submission(
        context=_context(),
        scope=_scope(),
        idempotency_key=f"analysis-register-{key_suffix}-0001",
        source_type="pdf",
        upload_id=str(intent["upload_id"]),
    )


def test_registration_executes_analysis_and_persists_ready_strategy() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service, object_storage, repository = _service(session)

        submitted = _register_document(
            service,
            object_storage,
            b"# Recovery\n\nDesigned an idempotent failover workflow.",
            key_suffix="ready",
        )

        assert submitted["status"] == "ready"
        readiness = service.get_readiness(context=_context(), scope=_scope())
        assert readiness["overall_status"] == "ready"
        assert readiness["interview_ready"] is True
        assert readiness["strategy_id"] is not None
        strategy = repository.latest_strategy(_context(), _scope())
        assert strategy is not None
        assert strategy.status.value == "ready"
        assert strategy.source_reference_candidates
        events = SQLAlchemyOutbox(session).pending(_context())
        assert events == ()


def test_empty_document_persists_partial_strategy_and_impact() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service, object_storage, repository = _service(session)

        submitted = _register_document(
            service,
            object_storage,
            b" ",
            key_suffix="partial",
        )

        assert submitted["status"] == "partial"
        assert submitted["failure_code"] == "NO_EXTRACTABLE_CONTENT"
        readiness = service.get_readiness(context=_context(), scope=_scope())
        assert readiness["overall_status"] == "partial"
        assert readiness["interview_ready"] is True
        strategy = repository.latest_strategy(_context(), _scope())
        assert strategy is not None
        assert strategy.status.value == "partial"


def test_analysis_failure_persists_failed_readiness_without_strategy() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        service, object_storage, repository = _service(
            session,
            criterion_snapshot_provider=_failing_criterion_snapshot,
        )

        submitted = _register_document(
            service,
            object_storage,
            b"analysis input",
            key_suffix="failed",
        )

        assert submitted["status"] == "failed"
        assert submitted["failure_code"] == ErrorCode.INVALID_REQUEST.value
        readiness = service.get_readiness(context=_context(), scope=_scope())
        assert readiness["overall_status"] == "failed"
        assert readiness["interview_ready"] is False
        assert repository.latest_strategy(_context(), _scope()) is None
