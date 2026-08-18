from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from interview_evidence.shared.aws_clients.ports import FakeObjectStorage, ProtectedBytes
from interview_evidence.shared.database import Base
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, TenantScopeViolation
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.adapters.search import (
    InMemorySubmissionSearch,
    SearchRecord,
)
from interview_evidence.submission_analysis.application.authorization import (
    SubmissionAuthorizationGate,
)
from interview_evidence.submission_analysis.application.deletion_targets import (
    SubmissionDeletionService,
)
from interview_evidence.submission_analysis.application.retrieval import (
    HybridRetriever,
    RetrievalQuery,
)
from interview_evidence.submission_analysis.application.strategy_service import StrategyService
from interview_evidence.submission_analysis.application.submission_service import (
    SubmissionApplicationService,
)
from interview_evidence.submission_analysis.application.submission_validator import (
    SubmissionValidator,
)
from interview_evidence.submission_analysis.contracts import SubmissionAnalysisPublicService
from interview_evidence.submission_analysis.domain.source import SourceReference
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)
from interview_evidence.workers.analysis.document_chunker import DocumentChunker
from interview_evidence.workers.analysis.document_extract import DocumentExtractor
from interview_evidence.workers.analysis.git_fetch import GitFetchLimits, PublicRepositoryFetcher
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    CRITERION_ID,
    INVITATION_ID,
    make_criterion_snapshot,
    make_other_tenant_context,
    make_tenant_context,
)
from tests.fixtures.shared.module_fakes import DeterministicModuleFakes


def _context() -> TenantContext:
    return TenantContext(**make_tenant_context())


def _scope() -> ApplicantScope:
    return ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)


def _ids(clock: FixedClock) -> UUID7Generator:
    return UUID7Generator(clock, randbytes=lambda size: b"\x31" * size)


def test_lane_b_quickstart_creates_scoped_strategy_and_deletes_derived_data() -> None:
    clock = FixedClock(datetime(2026, 8, 17, tzinfo=UTC))
    ids = _ids(clock)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    from interview_evidence.submission_analysis.repositories import postgres as _submission_models

    del _submission_models
    Base.metadata.create_all(engine)
    session = Session(engine)
    try:
        repository = SubmissionAnalysisRepository(session)
        object_storage = SubmissionObjectStorage(FakeObjectStorage(), clock=clock, id_generator=ids)
        search = InMemorySubmissionSearch()
        service = SubmissionApplicationService(
            repository=repository,
            authorization=SubmissionAuthorizationGate(
                DeterministicModuleFakes(company_id=COMPANY_ID)
            ),
            object_storage=object_storage,
            validator=SubmissionValidator(max_file_bytes=2_000_000),
            clock=clock,
            id_generator=ids,
        )

        document_content = "# 프로젝트\n\n장애 복구 경험".encode()
        intent = service.create_upload_intent(
            context=_context(),
            scope=_scope(),
            idempotency_key="lane-b-upload-intent-0001",
            source_type="pdf",
            filename="portfolio.pdf",
            media_type="application/pdf",
            byte_size=len(document_content),
            sha256=hashlib.sha256(document_content).hexdigest(),
        )
        assert intent["url"] != "https://uploads.invalid"
        object_storage.accept_upload(
            _context(),
            _scope(),
            upload_id=intent["upload_id"],
            content=ProtectedBytes(document_content),
            media_type="application/pdf",
        )
        submitted = service.register_submission(
            context=_context(),
            scope=_scope(),
            idempotency_key="lane-b-register-0001",
            source_type="pdf",
            upload_id=intent["upload_id"],
        )
        submission_id = submitted["submission_id"]

        extracted = DocumentExtractor().extract(
            object_storage.read_upload(_context(), _scope(), intent["upload_id"]),
            media_type="application/pdf",
        )
        chunk = DocumentChunker(max_characters=64, overlap_characters=8).chunk(extracted)[0]
        source = SourceReference(
            company_id=COMPANY_ID,
            source_type="submission_chunk",
            source_id=ids.new(),
            source_version=1,
            source_location=chunk.location,
            source_hash=chunk.chunk_hash,
        )
        search.index(
            _context(),
            SearchRecord(
                scope=_scope(),
                reference=source,
                text=chunk.text.reveal(),
                vector=(1.0, 0.0),
                symbols=(),
            ),
        )
        repository.record_source_reference(
            _context(), _scope(), submission_id=submission_id, reference=source
        )

        strategy = StrategyService(clock=clock, id_generator=ids).generate(
            _context(),
            scope=_scope(),
            criterion_snapshot=make_criterion_snapshot(),
            verification_points=(
                {"criterion_id": CRITERION_ID, "prompt": "장애 복구 판단을 확인"},
            ),
            source_references=(source,),
            duration_minutes=30,
            model_config_version="strategy-v1",
            partial=False,
        )
        repository.add_strategy(_context(), strategy)
        repository.mark_submission_ready(_context(), submission_id)

        readiness = service.get_readiness(context=_context(), scope=_scope())
        assert readiness["overall_status"] == "ready"
        assert readiness["interview_ready"] is True
        assert readiness["strategy_id"] == str(strategy.interview_strategy_id)

        retriever = HybridRetriever(search)
        retrieved = retriever.retrieve(
            _context(),
            RetrievalQuery(
                scope=_scope(),
                query_text="장애 복구",
                query_vector=(1.0, 0.0),
                criterion_id=CRITERION_ID,
                interview_session_id="018f2000-0000-7000-8000-000000000230",
                config_version="hybrid-v1",
            ),
        )
        assert retrieved.results[0].source_reference.source_id == source.source_id

        deletion = SubmissionDeletionService(repository, object_storage, search)
        public = SubmissionAnalysisPublicService(repository, retriever, deletion)
        status_snapshot = public.get_analysis_status(_context(), invitation_id=INVITATION_ID)
        strategy_snapshot = public.get_strategy_snapshot(
            _context(), strategy_id=strategy.interview_strategy_id
        )
        source_snapshot = public.resolve_source_reference(_context(), source_id=source.source_id)
        assert status_snapshot["strategy_ready"] is True
        assert (
            strategy_snapshot["competency_model_version_id"]
            == make_criterion_snapshot()["competency_model_version_id"]
        )
        assert source_snapshot["evidence_eligible"] is False

        targets = deletion.enumerate_targets(_context(), _scope())
        assert {target.store for target in targets} == {"aurora", "s3", "opensearch"}
        receipts = [deletion.delete_target(_context(), _scope(), target) for target in targets]
        assert all(receipt.status == "verified_absent" for receipt in receipts)

        with pytest.raises(TenantScopeViolation):
            repository.list_submissions(TenantContext(**make_other_tenant_context()), _scope())
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_public_git_fetch_is_bounded_and_excludes_dependency_trees() -> None:
    snapshot = PublicRepositoryFetcher(
        limits=GitFetchLimits(max_files=2, max_total_bytes=64, max_file_bytes=40)
    ).fetch(
        "https://github.com/example/public-repo",
        head_sha="a" * 40,
        files={
            "src/app.py": b"print('ok')",
            "tests/test_app.py": b"def test_app(): pass",
            "node_modules/pkg/index.js": b"ignored",
        },
    )

    assert snapshot.pinned_head_sha == "a" * 40
    assert set(snapshot.files) == {"src/app.py", "tests/test_app.py"}
