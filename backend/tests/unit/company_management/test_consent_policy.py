from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from interview_evidence.company_management.domain.applicant_access import (
    ConsentPurpose,
    ConsentRecord,
    ProcessingAuthorization,
)
from interview_evidence.company_management.domain.hiring import Invitation, InvitationState
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ActorType, TenantContext

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000001")
CAMPAIGN_ID = "0198b6c5-8800-7000-8000-000000000006"
INVITATION_ID = "0198b6c5-8800-7000-8000-000000000007"
APPLICANT_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000008")
CONSENT_ID = "0198b6c5-8800-7000-8000-000000000009"


def _context(actor_id: str | OpaqueId = APPLICANT_ID) -> TenantContext:
    return TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.APPLICANT,
        actor_id=OpaqueId(actor_id),
        request_id=OpaqueId("0198b6c5-8800-7000-8000-000000000010"),
        trace_id="trace-consent-policy",
    )


def _invitation() -> Invitation:
    invitation, _ = Invitation.issue(
        invitation_id=INVITATION_ID,
        company_id=COMPANY_ID,
        campaign_id=CAMPAIGN_ID,
        applicant_id=APPLICANT_ID,
        applicant_email="candidate@example.com",
        expires_at=NOW + timedelta(days=7),
    )
    return invitation.transition(
        InvitationState.IDENTITY_VERIFIED,
        idempotency_key="identity-verified-0001",
        occurred_at=NOW,
    )


def _consent() -> ConsentRecord:
    return ConsentRecord.accept(
        consent_record_id=CONSENT_ID,
        company_id=COMPANY_ID,
        invitation_id=INVITATION_ID,
        applicant_id=APPLICANT_ID,
        policy_version="consent-v1",
        purposes=frozenset(ConsentPurpose),
        retention_days=180,
        accepted_at=NOW,
        displayed_content="문서 분석, 녹화, AI 평가에 동의합니다.",
    )


def test_processing_is_denied_before_consent_and_after_withdrawal() -> None:
    invitation = _invitation()

    with pytest.raises(SafeApplicationError) as missing:
        ProcessingAuthorization.require(
            invitation=invitation,
            consent=None,
            purpose=ConsentPurpose.DOCUMENT_ANALYSIS,
            now=NOW,
        )
    assert missing.value.code is ErrorCode.FORBIDDEN

    consent = _consent()
    ProcessingAuthorization.require(
        invitation=invitation,
        consent=consent,
        purpose=ConsentPurpose.RECORDING,
        now=NOW,
    )

    withdrawn = consent.withdraw(_context(), NOW)
    with pytest.raises(SafeApplicationError) as stopped:
        ProcessingAuthorization.require(
            invitation=invitation,
            consent=withdrawn,
            purpose=ConsentPurpose.AI_ASSESSMENT,
            now=NOW,
        )
    assert stopped.value.code is ErrorCode.FORBIDDEN


def test_only_the_scoped_applicant_can_withdraw_consent() -> None:
    with pytest.raises(SafeApplicationError) as denied:
        _consent().withdraw(
            _context("0198b6c5-8800-7000-8000-000000000099"),
            NOW,
        )
    assert denied.value.code is ErrorCode.TENANT_SCOPE_DENIED
