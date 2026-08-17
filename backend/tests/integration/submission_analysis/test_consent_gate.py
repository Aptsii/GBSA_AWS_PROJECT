from __future__ import annotations

from copy import deepcopy

import pytest

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.submission_analysis.application.authorization import (
    SubmissionAuthorizationGate,
)
from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_tenant_context,
)


class _CompanyContractStub:
    def __init__(self) -> None:
        self.invitation = {
            "company_id": COMPANY_ID,
            "invitation_id": INVITATION_ID,
            "applicant_id": APPLICANT_ID,
            "campaign_id": "018f2000-0000-7000-8000-000000000200",
            "state": "consented",
            "expires_at": "2026-08-20T00:00:00Z",
            "authorized": True,
            "reason_code": None,
        }
        self.consent = {
            "company_id": COMPANY_ID,
            "invitation_id": INVITATION_ID,
            "consent_record_id": "018f2000-0000-7000-8000-000000000212",
            "policy_version": "privacy-v1",
            "purpose_codes": ["document_analysis", "recording", "ai_assessment"],
            "retention_days": 180,
            "accepted_at": "2026-08-17T00:00:00Z",
            "withdrawn_at": None,
            "authorized": True,
            "reason_code": None,
        }

    def authorize_invitation(self, _context: TenantContext, **_: object) -> dict[str, object]:
        return deepcopy(self.invitation)

    def get_consent_authorization(self, _context: TenantContext, **_: object) -> dict[str, object]:
        return deepcopy(self.consent)


def _context() -> TenantContext:
    return TenantContext(**make_tenant_context())


def _scope() -> ApplicantScope:
    return ApplicantScope(
        company_id=COMPANY_ID,
        applicant_id=APPLICANT_ID,
        invitation_id=INVITATION_ID,
    )


def test_gate_allows_only_active_invitation_with_document_analysis_consent() -> None:
    contracts = _CompanyContractStub()
    snapshot = SubmissionAuthorizationGate(contracts).authorize(_context(), _scope())

    assert snapshot.consent_record_id.endswith("212")
    assert snapshot.retention_days == 180


@pytest.mark.parametrize("mutation", ["invitation", "missing_purpose", "withdrawn"])
def test_gate_rejects_invalid_invitation_or_consent(mutation: str) -> None:
    contracts = _CompanyContractStub()
    if mutation == "invitation":
        contracts.invitation["authorized"] = False
        contracts.invitation["reason_code"] = "INVITATION_REVOKED"
    elif mutation == "missing_purpose":
        contracts.consent["purpose_codes"] = ["recording", "ai_assessment"]
    else:
        contracts.consent["withdrawn_at"] = "2026-08-17T00:30:00Z"

    with pytest.raises(SafeApplicationError) as caught:
        SubmissionAuthorizationGate(contracts).authorize(_context(), _scope())

    assert caught.value.code is ErrorCode.FORBIDDEN
