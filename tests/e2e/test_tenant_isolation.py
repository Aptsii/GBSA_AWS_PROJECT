from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from interview_evidence.interview_engine.application.checkpoints import CheckpointService
from interview_evidence.interview_engine.domain.session import SessionState
from interview_evidence.main import create_app
from interview_evidence.shared.aws_clients.ports import (
    FakeObjectStorage,
    ObjectRef,
    ProtectedBytes,
)
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import (
    ApplicantScope,
    TenantContext,
    TenantScopeViolation,
    ensure_company_scope,
)
from interview_evidence.submission_analysis.adapters.search import (
    InMemorySubmissionSearch,
    SearchRecord,
)
from interview_evidence.submission_analysis.domain.source import SourceLocation, SourceReference
from interview_evidence.workers.analysis.handlers import AnalysisJob, AnalysisJobHandler

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    OTHER_COMPANY_ID,
    make_other_tenant_context,
    make_tenant_context,
)


@pytest.mark.asyncio
async def test_route_worker_search_object_and_hot_view_deny_other_tenant() -> None:
    owner = TenantContext(**make_tenant_context())
    other = TenantContext(**make_other_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    session_id = OpaqueId("018f2000-0000-7000-8000-000000000730")

    router = APIRouter()

    @router.get("/tenant-resource/{company_id}")
    def tenant_resource(company_id: str) -> dict[str, str]:
        ensure_company_scope(other, company_id)
        return {"company_id": company_id}

    response = TestClient(create_app((router,))).get(f"/v1/tenant-resource/{COMPANY_ID}")
    assert response.status_code == 403
    assert response.json()["code"] == "TENANT_SCOPE_DENIED"

    job = AnalysisJob(
        company_id=COMPANY_ID,
        scope=scope,
        submission_id="018f2000-0000-7000-8000-000000000731",
        analysis_version=1,
        source_type="pdf",
        idempotency_key="tenant-isolation-job-0001",
    )
    with pytest.raises(TenantScopeViolation):
        AnalysisJobHandler().handle(other, job, lambda _job: pytest.fail("must not run"))

    source = SourceReference(
        company_id=COMPANY_ID,
        source_type="submission_chunk",
        source_id="018f2000-0000-7000-8000-000000000732",
        source_version=1,
        source_location=SourceLocation(page=1),
        source_hash="1" * 64,
    )
    search = InMemorySubmissionSearch()
    search.index(owner, SearchRecord(scope, source, "tenant text", (1.0,), ()))
    with pytest.raises(TenantScopeViolation):
        search.candidates(other, scope)

    storage = FakeObjectStorage()
    reference = ObjectRef(
        company_id=COMPANY_ID,
        object_id="018f2000-0000-7000-8000-000000000733",
        applicant_scope=scope,
    )
    await storage.put(owner, reference, ProtectedBytes(b"protected"), media_type="text/plain")
    with pytest.raises(TenantScopeViolation):
        await storage.get(other, reference)

    clock = FixedClock(datetime(2026, 8, 17, tzinfo=UTC))
    checkpoints = CheckpointService(clock=clock, id_generator=UUID7Generator(clock))
    checkpoints.record(
        owner,
        scope,
        session_id,
        session_sequence=3,
        last_final_turn_id=None,
        last_media_chunk_sequence=1,
        state=SessionState.PAUSED,
    )
    with pytest.raises(TenantScopeViolation):
        checkpoints.resume(other, scope, session_id, client_sequence=2)

    assert str(other.company_id) == OTHER_COMPANY_ID
