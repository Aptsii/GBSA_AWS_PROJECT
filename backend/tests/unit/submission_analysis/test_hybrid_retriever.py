from __future__ import annotations

from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.submission_analysis.adapters.search import (
    InMemorySubmissionSearch,
    SearchRecord,
)
from interview_evidence.submission_analysis.application.retrieval import (
    HybridRetriever,
    RetrievalQuery,
)
from interview_evidence.submission_analysis.domain.source import SourceLocation, SourceReference
from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    CRITERION_ID,
    INVITATION_ID,
    make_tenant_context,
)


def _context() -> TenantContext:
    return TenantContext(**make_tenant_context())


def _scope() -> ApplicantScope:
    return ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)


def _record(
    source_id: str, text: str, vector: tuple[float, ...], symbols: tuple[str, ...]
) -> SearchRecord:
    return SearchRecord(
        scope=_scope(),
        reference=SourceReference(
            company_id=COMPANY_ID,
            source_type="candidate_code_unit",
            source_id=source_id,
            source_version=1,
            source_location=SourceLocation(
                path="src/payment.py", symbol=symbols[0] if symbols else None
            ),
            source_hash="b" * 64,
            ownership_confidence=0.9,
        ),
        text=text,
        vector=vector,
        symbols=symbols,
    )


def test_hybrid_ranking_combines_vector_lexical_and_exact_symbol_boost() -> None:
    index = InMemorySubmissionSearch()
    semantic_id = "018f2000-0000-7000-8000-000000000331"
    symbol_id = "018f2000-0000-7000-8000-000000000332"
    index.index(_context(), _record(semantic_id, "결제 재시도 설계", (1.0, 0.0), ("other",)))
    index.index(_context(), _record(symbol_id, "일반 설명", (0.6, 0.8), ("retry_payment",)))

    response = HybridRetriever(
        index, vector_weight=0.5, lexical_weight=0.3, exact_symbol_boost=0.4
    ).retrieve(
        _context(),
        RetrievalQuery(
            scope=_scope(),
            query_text="retry_payment 결제",
            query_vector=(1.0, 0.0),
            criterion_id=CRITERION_ID,
            interview_session_id="018f2000-0000-7000-8000-000000000230",
            config_version="hybrid-v1",
            exact_symbol="retry_payment",
        ),
    )

    assert response.results[0].source_reference.source_id == symbol_id
    assert response.results[0].score > response.results[1].score
