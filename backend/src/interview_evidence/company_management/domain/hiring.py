from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from interview_evidence.shared._validation import utc_instant
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class InvitationState(StrEnum):
    INVITED = "invited"
    IDENTITY_VERIFIED = "identity_verified"
    CONSENTED = "consented"
    MATERIALS_SUBMITTED = "materials_submitted"
    ANALYZING = "analyzing"
    READY = "ready"
    INTERVIEWING = "interviewing"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    REVIEWED = "reviewed"
    EXPIRED = "expired"
    REVOKED = "revoked"
    DELETED = "deleted"


_ALLOWED_TRANSITIONS: dict[InvitationState, frozenset[InvitationState]] = {
    InvitationState.INVITED: frozenset(
        {
            InvitationState.IDENTITY_VERIFIED,
            InvitationState.EXPIRED,
            InvitationState.REVOKED,
            InvitationState.DELETED,
        }
    ),
    InvitationState.IDENTITY_VERIFIED: frozenset(
        {
            InvitationState.CONSENTED,
            InvitationState.EXPIRED,
            InvitationState.REVOKED,
            InvitationState.DELETED,
        }
    ),
    InvitationState.CONSENTED: frozenset(
        {InvitationState.MATERIALS_SUBMITTED, InvitationState.REVOKED, InvitationState.DELETED}
    ),
    InvitationState.MATERIALS_SUBMITTED: frozenset(
        {InvitationState.ANALYZING, InvitationState.DELETED}
    ),
    InvitationState.ANALYZING: frozenset({InvitationState.READY, InvitationState.DELETED}),
    InvitationState.READY: frozenset({InvitationState.INTERVIEWING, InvitationState.DELETED}),
    InvitationState.INTERVIEWING: frozenset(
        {InvitationState.INTERRUPTED, InvitationState.COMPLETED, InvitationState.DELETED}
    ),
    InvitationState.INTERRUPTED: frozenset({InvitationState.INTERVIEWING, InvitationState.DELETED}),
    InvitationState.COMPLETED: frozenset({InvitationState.REVIEWED, InvitationState.DELETED}),
    InvitationState.REVIEWED: frozenset({InvitationState.DELETED}),
    InvitationState.EXPIRED: frozenset({InvitationState.DELETED}),
    InvitationState.REVOKED: frozenset({InvitationState.DELETED}),
    InvitationState.DELETED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Campaign:
    campaign_id: OpaqueId
    company_id: OpaqueId
    position_id: OpaqueId
    competency_model_version_id: OpaqueId
    name: str
    candidate_instructions: str
    status: CampaignStatus = CampaignStatus.DRAFT
    published_at: datetime | None = None
    closed_at: datetime | None = None
    row_version: int = 1
    invitations_issued: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "campaign_id",
            "company_id",
            "position_id",
            "competency_model_version_id",
        ):
            object.__setattr__(self, field_name, OpaqueId(getattr(self, field_name)))
        name = self.name.strip()
        instructions = self.candidate_instructions.strip()
        if not name or len(name) > 200:
            raise ValueError("campaign name must contain between 1 and 200 characters")
        if not instructions or len(instructions) > 10_000:
            raise ValueError("candidate instructions must be present")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "candidate_instructions", instructions)
        if not isinstance(self.status, CampaignStatus):
            object.__setattr__(self, "status", CampaignStatus(self.status))
        if self.published_at is not None:
            object.__setattr__(self, "published_at", utc_instant(self.published_at))
        if self.closed_at is not None:
            object.__setattr__(self, "closed_at", utc_instant(self.closed_at))
        if self.row_version < 1:
            raise ValueError("row_version must be positive")

    def publish(self, published_at: datetime) -> Campaign:
        if self.status is CampaignStatus.PUBLISHED:
            return self
        if self.status is not CampaignStatus.DRAFT:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return replace(
            self,
            status=CampaignStatus.PUBLISHED,
            published_at=utc_instant(published_at),
            row_version=self.row_version + 1,
        )

    def mark_invitation_issued(self) -> Campaign:
        if self.status is not CampaignStatus.PUBLISHED:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        if self.invitations_issued:
            return self
        return replace(self, invitations_issued=True, row_version=self.row_version + 1)

    def pin_competency_model_version(self, version_id: str | OpaqueId) -> Campaign:
        checked = OpaqueId(version_id)
        if checked == self.competency_model_version_id:
            return self
        if self.invitations_issued:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return replace(
            self,
            competency_model_version_id=checked,
            row_version=self.row_version + 1,
        )

    def to_view(self) -> dict[str, object]:
        return {
            "campaign_id": str(self.campaign_id),
            "position_id": str(self.position_id),
            "competency_model_version_id": str(self.competency_model_version_id),
            "name": self.name,
            "candidate_instructions": self.candidate_instructions,
            "status": self.status.value,
            "row_version": self.row_version,
            "published_at": (
                self.published_at.isoformat().replace("+00:00", "Z")
                if self.published_at is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class Invitation:
    invitation_id: OpaqueId
    company_id: OpaqueId
    campaign_id: OpaqueId
    applicant_id: OpaqueId
    applicant_email: str
    token_hash: str
    expires_at: datetime
    state: InvitationState = InvitationState.INVITED
    row_version: int = 1
    token_exchanged_at: datetime | None = None
    identity_verified_at: datetime | None = None
    applied_transitions: tuple[tuple[str, InvitationState], ...] = ()

    def __post_init__(self) -> None:
        for field_name in ("invitation_id", "company_id", "campaign_id", "applicant_id"):
            object.__setattr__(self, field_name, OpaqueId(getattr(self, field_name)))
        normalized_email = self.applicant_email.strip().lower()
        if "@" not in normalized_email or len(normalized_email) > 320:
            raise ValueError("applicant_email must be a valid normalized address")
        object.__setattr__(self, "applicant_email", normalized_email)
        if len(self.token_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.token_hash
        ):
            raise ValueError("token_hash must be a SHA-256 hex digest")
        object.__setattr__(self, "expires_at", utc_instant(self.expires_at))
        if not isinstance(self.state, InvitationState):
            object.__setattr__(self, "state", InvitationState(self.state))
        if self.row_version < 1:
            raise ValueError("row_version must be positive")
        if self.token_exchanged_at is not None:
            object.__setattr__(self, "token_exchanged_at", utc_instant(self.token_exchanged_at))
        if self.identity_verified_at is not None:
            object.__setattr__(self, "identity_verified_at", utc_instant(self.identity_verified_at))

    @classmethod
    def issue(
        cls,
        *,
        invitation_id: str | OpaqueId,
        company_id: str | OpaqueId,
        campaign_id: str | OpaqueId,
        applicant_id: str | OpaqueId,
        applicant_email: str,
        expires_at: datetime,
    ) -> tuple[Invitation, str]:
        raw_token = secrets.token_urlsafe(32)
        return (
            cls(
                invitation_id=OpaqueId(invitation_id),
                company_id=OpaqueId(company_id),
                campaign_id=OpaqueId(campaign_id),
                applicant_id=OpaqueId(applicant_id),
                applicant_email=applicant_email,
                token_hash=cls.digest_token(raw_token),
                expires_at=expires_at,
            ),
            raw_token,
        )

    @staticmethod
    def digest_token(raw_token: str) -> str:
        if not raw_token or len(raw_token) > 4_096:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def matches_token(self, raw_token: str) -> bool:
        return hmac.compare_digest(self.token_hash, self.digest_token(raw_token))

    def authorize_token(self, raw_token: str, now: datetime) -> Invitation:
        checked_now = utc_instant(now)
        if checked_now >= self.expires_at:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_EXPIRED)
        if self.token_exchanged_at is not None or self.state in {
            InvitationState.EXPIRED,
            InvitationState.REVOKED,
            InvitationState.DELETED,
        }:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        if not self.matches_token(raw_token):
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        return self

    def mark_token_exchanged(self, occurred_at: datetime) -> Invitation:
        if self.token_exchanged_at is not None:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        return replace(self, token_exchanged_at=utc_instant(occurred_at))

    def transition(
        self,
        state: InvitationState,
        *,
        idempotency_key: str,
        occurred_at: datetime,
    ) -> Invitation:
        target = InvitationState(state)
        for applied_key, applied_state in self.applied_transitions:
            if applied_key == idempotency_key:
                if applied_state is target:
                    return self
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        verified_at = self.identity_verified_at
        if target is InvitationState.IDENTITY_VERIFIED:
            verified_at = utc_instant(occurred_at)
        return replace(
            self,
            state=target,
            row_version=self.row_version + 1,
            identity_verified_at=verified_at,
            applied_transitions=(*self.applied_transitions, (idempotency_key, target)),
        )

    def to_view(self) -> dict[str, object]:
        return {
            "invitation_id": str(self.invitation_id),
            "campaign_id": str(self.campaign_id),
            "applicant_email": self.applicant_email,
            "status": self.state.value,
            "expires_at": self.expires_at.isoformat().replace("+00:00", "Z"),
            "row_version": self.row_version,
            "analysis_status": None,
            "interview_status": None,
            "report_status": None,
        }

    def __repr__(self) -> str:
        return (
            "Invitation("
            f"invitation_id={self.invitation_id!r}, company_id={self.company_id!r}, "
            f"campaign_id={self.campaign_id!r}, applicant_id={self.applicant_id!r}, "
            f"state={self.state.value!r}, row_version={self.row_version})"
        )
