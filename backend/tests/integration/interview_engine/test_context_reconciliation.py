from __future__ import annotations

from interview_evidence.interview_engine.adapters.recent_context import RecentContextView
from interview_evidence.interview_engine.application.context_reconciliation import ContextReconciler
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    SESSION_ID,
    make_tenant_context,
)


def test_reconciliation_updates_hot_view_and_falls_back_to_durable_turns() -> None:
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    view = RecentContextView()
    reconciler = ContextReconciler(view)
    reconciler.reconcile(context, scope, SESSION_ID, ({"turn_id": "t1", "sequence": 1},))
    assert reconciler.load(context, scope, SESSION_ID)[0]["turn_id"] == "t1"
    view.set_available(False)
    assert reconciler.load(context, scope, SESSION_ID)[0]["turn_id"] == "t1"
