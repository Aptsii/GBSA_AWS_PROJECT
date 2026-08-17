from __future__ import annotations

import pytest
from interview_evidence.reporting.application.review_service import ReviewService
from interview_evidence.shared.tenant import ActorType, TenantContext

from tests.fixtures.shared.factories import INVITATION_ID, make_tenant_context


def test_system_actor_cannot_create_final_decision() -> None:
    values = make_tenant_context()
    values["actor_type"] = ActorType.SYSTEM
    context = TenantContext(**values)
    with pytest.raises(PermissionError, match="human"):
        ReviewService().final_decision(
            context,
            invitation_id=INVITATION_ID,
            decision="advance",
            reason="AI가 선택함",
            idempotency_key="final-decision-0001",
        )
