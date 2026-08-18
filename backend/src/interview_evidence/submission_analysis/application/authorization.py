from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class CompanyAuthorizationContracts(Protocol):
    def authorize_invitation(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]: ...

    def get_consent_authorization(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]: ...

    def get_campaign_snapshot(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]: ...

    def get_criterion_version(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class SubmissionAuthorization:
    company_id: OpaqueId
    invitation_id: OpaqueId
    applicant_id: OpaqueId
    campaign_id: OpaqueId
    consent_record_id: OpaqueId
    retention_days: int
    policy_version: str


class SubmissionAuthorizationGate:
    __slots__ = ("_contracts",)

    def __init__(self, contracts: CompanyAuthorizationContracts) -> None:
        self._contracts = contracts

    def authorize(self, context: TenantContext, scope: ApplicantScope) -> SubmissionAuthorization:
        ensure_applicant_scope(context, scope)
        invitation = self._contracts.authorize_invitation(
            context,
            invitation_id=str(scope.invitation_id),
            required_state="consented",
        )
        consent = self._contracts.get_consent_authorization(
            context,
            invitation_id=str(scope.invitation_id),
            required_purposes=["document_analysis"],
        )
        invitation_valid = (
            invitation.get("authorized") is True
            and invitation.get("company_id") == str(scope.company_id)
            and invitation.get("applicant_id") == str(scope.applicant_id)
            and invitation.get("invitation_id") == str(scope.invitation_id)
            and invitation.get("state")
            in {"consented", "materials_submitted", "analyzing", "ready"}
        )
        purpose_codes = consent.get("purpose_codes")
        consent_valid = (
            consent.get("authorized") is True
            and consent.get("company_id") == str(scope.company_id)
            and consent.get("invitation_id") == str(scope.invitation_id)
            and consent.get("withdrawn_at") is None
            and isinstance(purpose_codes, list)
            and "document_analysis" in purpose_codes
        )
        if not invitation_valid or not consent_valid:
            raise SafeApplicationError(ErrorCode.FORBIDDEN)
        retention_days = consent.get("retention_days")
        if not isinstance(retention_days, int) or retention_days < 1:
            raise SafeApplicationError(ErrorCode.FORBIDDEN)
        return SubmissionAuthorization(
            company_id=OpaqueId(str(scope.company_id)),
            invitation_id=OpaqueId(str(scope.invitation_id)),
            applicant_id=OpaqueId(str(scope.applicant_id)),
            campaign_id=OpaqueId(str(invitation["campaign_id"])),
            consent_record_id=OpaqueId(str(consent["consent_record_id"])),
            retention_days=retention_days,
            policy_version=str(consent["policy_version"]),
        )
