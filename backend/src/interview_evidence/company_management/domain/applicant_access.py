from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from interview_evidence.company_management.domain.hiring import Invitation, InvitationState
from interview_evidence.shared._validation import utc_instant
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class ConsentPurpose(StrEnum):
    DOCUMENT_ANALYSIS = "document_analysis"
    RECORDING = "recording"
    AI_ASSESSMENT = "ai_assessment"


class VerificationMethod(StrEnum):
    EMAIL_LINK = "email_link"


@dataclass(frozen=True, slots=True)
class ApplicantProfile(ApplicantScope):
    display_name: str
    verification_method: VerificationMethod
    technology_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        ApplicantScope.__post_init__(self)
        display_name = self.display_name.strip()
        if not display_name or len(display_name) > 200:
            raise ValueError("display_name must contain between 1 and 200 characters")
        object.__setattr__(self, "display_name", display_name)
        if not isinstance(self.verification_method, VerificationMethod):
            object.__setattr__(
                self,
                "verification_method",
                VerificationMethod(self.verification_method),
            )
        object.__setattr__(
            self,
            "technology_tags",
            tuple(tag.strip() for tag in self.technology_tags if tag.strip()),
        )


@dataclass(frozen=True, slots=True)
class ConsentRecord(ApplicantScope):
    consent_record_id: OpaqueId
    policy_version: str
    purposes: frozenset[ConsentPurpose]
    retention_days: int
    accepted_at: datetime
    evidence_digest: str
    withdrawn_at: datetime | None = None

    def __post_init__(self) -> None:
        ApplicantScope.__post_init__(self)
        object.__setattr__(self, "consent_record_id", OpaqueId(self.consent_record_id))
        policy_version = self.policy_version.strip()
        if not policy_version or len(policy_version) > 128:
            raise ValueError("policy_version must be present")
        object.__setattr__(self, "policy_version", policy_version)
        object.__setattr__(
            self,
            "purposes",
            frozenset(ConsentPurpose(purpose) for purpose in self.purposes),
        )
        if self.retention_days < 1:
            raise ValueError("retention_days must be positive")
        object.__setattr__(self, "accepted_at", utc_instant(self.accepted_at))
        if len(self.evidence_digest) != 64:
            raise ValueError("evidence_digest must be a SHA-256 hex digest")
        if self.withdrawn_at is not None:
            object.__setattr__(self, "withdrawn_at", utc_instant(self.withdrawn_at))

    @classmethod
    def accept(
        cls,
        *,
        consent_record_id: str | OpaqueId,
        company_id: str | OpaqueId,
        invitation_id: str | OpaqueId,
        applicant_id: str | OpaqueId,
        policy_version: str,
        purposes: frozenset[ConsentPurpose],
        retention_days: int,
        accepted_at: datetime,
        displayed_content: str,
    ) -> ConsentRecord:
        return cls(
            consent_record_id=OpaqueId(consent_record_id),
            company_id=OpaqueId(company_id),
            invitation_id=OpaqueId(invitation_id),
            applicant_id=OpaqueId(applicant_id),
            policy_version=policy_version,
            purposes=purposes,
            retention_days=retention_days,
            accepted_at=accepted_at,
            evidence_digest=hashlib.sha256(displayed_content.encode("utf-8")).hexdigest(),
        )

    def withdraw(self, context: TenantContext, withdrawn_at: datetime) -> ConsentRecord:
        ensure_applicant_scope(context, self)
        if self.withdrawn_at is not None:
            return self
        return replace(self, withdrawn_at=utc_instant(withdrawn_at))

    def to_view(self) -> dict[str, object]:
        return {
            "consent_record_id": str(self.consent_record_id),
            "policy_version": self.policy_version,
            "purpose_codes": sorted(purpose.value for purpose in self.purposes),
            "retention_days": self.retention_days,
            "accepted_at": self.accepted_at.isoformat().replace("+00:00", "Z"),
            "withdrawn_at": (
                self.withdrawn_at.isoformat().replace("+00:00", "Z")
                if self.withdrawn_at is not None
                else None
            ),
        }


class ProcessingAuthorization:
    @staticmethod
    def require(
        *,
        invitation: Invitation,
        consent: ConsentRecord | None,
        purpose: ConsentPurpose,
        now: datetime,
    ) -> ConsentRecord:
        checked_now = utc_instant(now)
        if checked_now >= invitation.expires_at:
            raise SafeApplicationError(ErrorCode.FORBIDDEN)
        if invitation.state not in {
            InvitationState.IDENTITY_VERIFIED,
            InvitationState.CONSENTED,
            InvitationState.MATERIALS_SUBMITTED,
            InvitationState.ANALYZING,
            InvitationState.READY,
            InvitationState.INTERVIEWING,
            InvitationState.INTERRUPTED,
            InvitationState.COMPLETED,
            InvitationState.REVIEWED,
        }:
            raise SafeApplicationError(ErrorCode.FORBIDDEN)
        if (
            consent is None
            or consent.company_id != invitation.company_id
            or consent.invitation_id != invitation.invitation_id
            or consent.applicant_id != invitation.applicant_id
            or consent.withdrawn_at is not None
            or ConsentPurpose(purpose) not in consent.purposes
        ):
            raise SafeApplicationError(ErrorCode.FORBIDDEN)
        return consent
