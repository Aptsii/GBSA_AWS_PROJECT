from __future__ import annotations

import pytest
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, TenantScopeViolation
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
    OTHER_COMPANY_ID,
    make_other_tenant_context,
    make_tenant_context,
)


def _context(factory: object = make_tenant_context) -> TenantContext:
    return TenantContext(**factory())  # type: ignore[operator]


def _scope(company_id: str = COMPANY_ID) -> ApplicantScope:
    return ApplicantScope(
        company_id=company_id,
        applicant_id=APPLICANT_ID,
        invitation_id=INVITATION_ID,
    )


def _record(company_id: str, source_id: str, text: str) -> SearchRecord:
    return SearchRecord(
        scope=_scope(company_id),
        reference=SourceReference(
            company_id=company_id,
            source_type="submission_chunk",
            source_id=source_id,
            source_version=1,
            source_location=SourceLocation(page=1, section="경험", start_offset=0),
            source_hash="a" * 64,
        ),
        text=text,
        vector=(1.0, 0.0),
        symbols=(),
    )


def test_retrieval_prefilters_company_and_applicant_scope() -> None:
    index = InMemorySubmissionSearch()
    own_id = "018f2000-0000-7000-8000-000000000321"
    other_id = "018f2000-0000-7000-8000-000000000921"
    index.index(_context(), _record(COMPANY_ID, own_id, "PostgreSQL 장애 복구"))
    index.index(
        _context(make_other_tenant_context),
        _record(OTHER_COMPANY_ID, other_id, "PostgreSQL 장애 복구"),
    )

    result = HybridRetriever(index).retrieve(
        _context(),
        RetrievalQuery(
            scope=_scope(),
            query_text="PostgreSQL 복구",
            query_vector=(1.0, 0.0),
            criterion_id=CRITERION_ID,
            interview_session_id="018f2000-0000-7000-8000-000000000230",
            config_version="hybrid-v1",
        ),
    )

    assert [item.source_reference.source_id for item in result.results] == [own_id]


def test_retrieval_rejects_cross_tenant_scope_before_search() -> None:
    with pytest.raises(TenantScopeViolation):
        HybridRetriever(InMemorySubmissionSearch()).retrieve(
            _context(),
            RetrievalQuery(
                scope=_scope(OTHER_COMPANY_ID),
                query_text="anything",
                query_vector=(1.0, 0.0),
                criterion_id=CRITERION_ID,
                interview_session_id="018f2000-0000-7000-8000-000000000230",
                config_version="hybrid-v1",
            ),
        )
