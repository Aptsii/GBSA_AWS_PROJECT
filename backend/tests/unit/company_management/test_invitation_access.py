from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from interview_evidence.company_management.domain.hiring import Invitation, InvitationState
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = "0198b6c5-8800-7000-8000-000000000001"
CAMPAIGN_ID = "0198b6c5-8800-7000-8000-000000000006"
INVITATION_ID = "0198b6c5-8800-7000-8000-000000000007"
APPLICANT_ID = "0198b6c5-8800-7000-8000-000000000008"


def _issued() -> tuple[Invitation, str]:
    return Invitation.issue(
        invitation_id=INVITATION_ID,
        company_id=COMPANY_ID,
        campaign_id=CAMPAIGN_ID,
        applicant_id=APPLICANT_ID,
        applicant_email="candidate@example.com",
        expires_at=NOW + timedelta(days=7),
    )


def test_invitation_persists_only_a_high_entropy_token_hash() -> None:
    invitation, raw_token = _issued()

    assert len(raw_token) >= 43
    assert len(invitation.token_hash) == 64
    assert raw_token not in invitation.token_hash
    assert raw_token not in repr(invitation)
    assert invitation.matches_token(raw_token)


def test_expired_or_reused_invitation_token_is_denied() -> None:
    invitation, raw_token = _issued()

    with pytest.raises(SafeApplicationError) as expired:
        invitation.authorize_token(raw_token, invitation.expires_at)
    assert expired.value.code is ErrorCode.AUTHENTICATION_EXPIRED

    authorized = invitation.authorize_token(raw_token, NOW)
    used = authorized.mark_token_exchanged(NOW)
    with pytest.raises(SafeApplicationError) as reused:
        used.authorize_token(raw_token, NOW)
    assert reused.value.code is ErrorCode.AUTHENTICATION_REQUIRED


def test_invitation_state_transitions_are_versioned_and_idempotent() -> None:
    invitation, _ = _issued()

    verified = invitation.transition(
        InvitationState.IDENTITY_VERIFIED,
        idempotency_key="identity-verified-0001",
        occurred_at=NOW,
    )
    repeated = verified.transition(
        InvitationState.IDENTITY_VERIFIED,
        idempotency_key="identity-verified-0001",
        occurred_at=NOW,
    )

    assert verified.row_version == 2
    assert repeated == verified
    with pytest.raises(SafeApplicationError) as invalid:
        verified.transition(
            InvitationState.COMPLETED,
            idempotency_key="invalid-transition-0001",
            occurred_at=NOW,
        )
    assert invalid.value.code is ErrorCode.CONFLICT
