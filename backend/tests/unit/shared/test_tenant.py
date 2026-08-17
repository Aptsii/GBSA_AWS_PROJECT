from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interview_evidence.shared.errors import ErrorCode
from interview_evidence.shared.tenant import (
    ActorType,
    ApplicantScope,
    EntityRef,
    TenantContext,
    TenantContextRequiredError,
    TenantScopeViolation,
    ensure_applicant_scope,
    ensure_company_scope,
    ensure_entity_scope,
    require_tenant_context,
)

COMPANY_ID = "0198a82a-0540-7000-8000-000000000001"
OTHER_COMPANY_ID = "0198a82a-0540-7000-8000-000000000002"
APPLICANT_ID = "0198a82a-0540-7000-8000-000000000003"
INVITATION_ID = "0198a82a-0540-7000-8000-000000000004"


def _applicant_context() -> TenantContext:
    return TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.APPLICANT,
        actor_id=APPLICANT_ID,
        request_id="0198a82a-0540-7000-8000-000000000005",
        trace_id="trace-0001",
    )


def test_missing_context_and_cross_tenant_access_are_safe_errors() -> None:
    with pytest.raises(TenantContextRequiredError) as missing:
        require_tenant_context(None)
    assert missing.value.code is ErrorCode.TENANT_CONTEXT_REQUIRED

    with pytest.raises(TenantScopeViolation) as denied:
        ensure_company_scope(_applicant_context(), OTHER_COMPANY_ID)

    assert denied.value.code is ErrorCode.TENANT_SCOPE_DENIED
    assert COMPANY_ID not in str(denied.value)
    assert OTHER_COMPANY_ID not in str(denied.value)


def test_entity_and_applicant_scope_require_matching_tenant_and_applicant() -> None:
    context = _applicant_context()
    entity = EntityRef(
        company_id=COMPANY_ID,
        entity_type="submission",
        entity_id="0198a82a-0540-7000-8000-000000000006",
        version=2,
    )
    applicant_scope = ApplicantScope(
        company_id=COMPANY_ID,
        applicant_id=APPLICANT_ID,
        invitation_id=INVITATION_ID,
    )

    assert ensure_entity_scope(context, entity) is entity
    assert ensure_applicant_scope(context, applicant_scope) is applicant_scope

    wrong_applicant = ApplicantScope(
        company_id=COMPANY_ID,
        applicant_id="0198a82a-0540-7000-8000-000000000099",
        invitation_id=INVITATION_ID,
    )
    with pytest.raises(TenantScopeViolation):
        ensure_applicant_scope(context, wrong_applicant)


def test_tenant_structures_are_validated_and_immutable() -> None:
    with pytest.raises(ValueError, match="positive"):
        EntityRef(
            company_id=COMPANY_ID,
            entity_type="submission",
            entity_id=APPLICANT_ID,
            version=0,
        )

    with pytest.raises(ValueError, match="trace_id"):
        TenantContext(
            company_id=COMPANY_ID,
            actor_type=ActorType.SYSTEM,
            actor_id=APPLICANT_ID,
            request_id=INVITATION_ID,
            trace_id="contains whitespace",
        )

    assert datetime.now(UTC).tzinfo is UTC
