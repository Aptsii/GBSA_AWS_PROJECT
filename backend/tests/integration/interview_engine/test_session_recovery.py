from __future__ import annotations

from interview_evidence.interview_engine.application.checkpoints import CheckpointService
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    SESSION_ID,
    make_tenant_context,
)


def test_resume_uses_latest_checkpoint_without_duplicate_turn() -> None:
    service = CheckpointService()
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    service.record(
        context,
        scope,
        SESSION_ID,
        session_sequence=3,
        last_final_turn_id="018f2000-0000-7000-8000-000000000233",
        last_media_chunk_sequence=2,
    )
    snapshot = service.resume(context, scope, SESSION_ID, client_sequence=1)
    assert snapshot.server_sequence == 3
    assert snapshot.last_final_turn_id.endswith("233")
    assert snapshot.stale_client is True
