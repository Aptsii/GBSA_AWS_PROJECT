from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock
from interview_evidence.shared.security.principals import (
    ApplicantPrincipal,
    CompanyPrincipal,
    FakeApplicantAuthenticator,
    FakeCompanyAuthenticator,
)
from interview_evidence.shared.tenant import ActorType

NOW = datetime(2026, 8, 14, 12, 30, tzinfo=UTC)
COMPANY_ID = "0198a82a-0540-7000-8000-000000000001"
ACTOR_ID = "0198a82a-0540-7000-8000-000000000003"


def test_company_auth_fake_hashes_credentials_and_builds_tenant_context() -> None:
    credential = "company-bearer-token-that-must-not-leak"
    principal = CompanyPrincipal(
        company_id=COMPANY_ID,
        company_user_id=ACTOR_ID,
        identity_subject="identity-provider-subject",
        roles=frozenset({"reviewer"}),
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    authenticator = FakeCompanyAuthenticator(FixedClock(NOW))
    authenticator.register(credential, principal)

    authenticated = authenticator.authenticate(credential)
    context = authenticated.to_tenant_context(
        request_id="0198a82a-0540-7000-8000-000000000005",
        trace_id="trace-0001",
    )

    assert authenticated == principal
    assert context.actor_type is ActorType.COMPANY_USER
    assert context.actor_id == ACTOR_ID
    assert credential not in repr(authenticator)


def test_applicant_auth_fake_enforces_expiry_and_invitation_scope() -> None:
    credential = "applicant-cookie-token-that-must-not-leak"
    principal = ApplicantPrincipal(
        company_id=COMPANY_ID,
        applicant_id=ACTOR_ID,
        invitation_id="0198a82a-0540-7000-8000-000000000004",
        session_id="0198a82a-0540-7000-8000-000000000006",
        issued_at=NOW - timedelta(hours=1),
        expires_at=NOW - timedelta(seconds=1),
    )
    authenticator = FakeApplicantAuthenticator(FixedClock(NOW))
    authenticator.register(credential, principal)

    with pytest.raises(SafeApplicationError) as expired:
        authenticator.authenticate(credential)
    assert expired.value.code is ErrorCode.AUTHENTICATION_EXPIRED

    with pytest.raises(SafeApplicationError) as unknown:
        authenticator.authenticate("unknown-applicant-credential")
    assert unknown.value.code is ErrorCode.AUTHENTICATION_REQUIRED


def test_principal_expiry_must_follow_issue_time() -> None:
    with pytest.raises(ValueError, match="expires_at"):
        CompanyPrincipal(
            company_id=COMPANY_ID,
            company_user_id=ACTOR_ID,
            identity_subject="subject",
            roles=frozenset(),
            issued_at=NOW,
            expires_at=NOW,
        )
