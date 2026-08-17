from __future__ import annotations

from interview_evidence.interview_engine.application.idempotency import ScopedIdempotencyStore
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_tenant_context,
)


def test_scoped_idempotency_replays_same_command_once() -> None:
    store = ScopedIdempotencyStore()
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    calls = 0

    def execute() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"sequence": 4}

    first = store.execute(context, scope, "answer-complete-0001", {"turn": "t1"}, execute)
    replay = store.execute(context, scope, "answer-complete-0001", {"turn": "t1"}, execute)
    assert replay == first
    assert calls == 1
