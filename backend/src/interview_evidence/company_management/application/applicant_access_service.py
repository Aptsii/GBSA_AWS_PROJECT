from __future__ import annotations

from collections.abc import Iterable

from interview_evidence.company_management.domain.applicant_access import (
    ApplicantProfile,
    ConsentPurpose,
    ConsentRecord,
    VerificationMethod,
)
from interview_evidence.company_management.domain.hiring import InvitationState
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
)
from interview_evidence.shared.ids import Clock, UUID7Generator
from interview_evidence.shared.security.principals import ApplicantPrincipal
from interview_evidence.shared.tenant import TenantContext, ensure_applicant_scope


class ApplicantAccessService:
    def __init__(
        self,
        repository: CompanyManagementRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
        retention_days: int = 180,
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.id_generator = id_generator
        self.retention_days = retention_days

    def verify_identity(
        self,
        context: TenantContext,
        principal: ApplicantPrincipal,
        *,
        display_name: str,
        verification_value: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        ensure_applicant_scope(context, principal.applicant_scope())
        if not verification_value.strip():
            raise ValueError("verification_value must be present")
        invitation = self.repository.get_invitation(context, principal.invitation_id)
        profile = ApplicantProfile(
            applicant_id=principal.applicant_id,
            company_id=principal.company_id,
            invitation_id=principal.invitation_id,
            display_name=display_name,
            verification_method=VerificationMethod.EMAIL_LINK,
        )
        self.repository.add_applicant_profile(context, profile)
        verified = invitation.transition(
            InvitationState.IDENTITY_VERIFIED,
            idempotency_key=idempotency_key,
            occurred_at=self.clock.now(),
        )
        self.repository.add_invitation(context, verified)
        return {
            "invitation_id": str(verified.invitation_id),
            "state": verified.state.value,
            "expires_at": verified.expires_at.isoformat().replace("+00:00", "Z"),
            "required_actions": ["consent"],
        }

    def record_consent(
        self,
        context: TenantContext,
        principal: ApplicantPrincipal,
        *,
        policy_version: str,
        accepted_purposes: Iterable[str],
        consent_content_digest: str,
        idempotency_key: str,
    ) -> ConsentRecord:
        ensure_applicant_scope(context, principal.applicant_scope())
        invitation = self.repository.get_invitation(context, principal.invitation_id)
        purposes = frozenset(ConsentPurpose(value) for value in accepted_purposes)
        consent = ConsentRecord(
            consent_record_id=self.id_generator.new(),
            company_id=principal.company_id,
            invitation_id=principal.invitation_id,
            applicant_id=principal.applicant_id,
            policy_version=policy_version,
            purposes=purposes,
            retention_days=self.retention_days,
            accepted_at=self.clock.now(),
            evidence_digest=consent_content_digest,
        )
        self.repository.add_consent(context, consent)
        consented = invitation.transition(
            InvitationState.CONSENTED,
            idempotency_key=idempotency_key,
            occurred_at=self.clock.now(),
        )
        self.repository.add_invitation(context, consented)
        return consent


def consent_authorization_snapshot(consent: ConsentRecord) -> dict[str, object]:
    return {
        "company_id": str(consent.company_id),
        "invitation_id": str(consent.invitation_id),
        "consent_record_id": str(consent.consent_record_id),
        "policy_version": consent.policy_version,
        "purpose_codes": sorted(purpose.value for purpose in consent.purposes),
        "retention_days": consent.retention_days,
        "accepted_at": consent.accepted_at.isoformat().replace("+00:00", "Z"),
        "withdrawn_at": (
            consent.withdrawn_at.isoformat().replace("+00:00", "Z")
            if consent.withdrawn_at is not None
            else None
        ),
        "authorized": consent.withdrawn_at is None,
        "reason_code": None if consent.withdrawn_at is None else "consent_withdrawn",
    }
