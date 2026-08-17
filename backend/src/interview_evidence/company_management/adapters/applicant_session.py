from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from interview_evidence.company_management.domain.hiring import Invitation
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, UUID7Generator
from interview_evidence.shared.security.principals import ApplicantPrincipal
from interview_evidence.shared.tenant import ActorType, TenantContext


class ApplicantSessionAdapter:
    __slots__ = ("_clock", "_id_generator", "_repository", "_sessions")

    def __init__(
        self,
        repository: CompanyManagementRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._id_generator = id_generator
        self._sessions: dict[str, ApplicantPrincipal] = {}

    def exchange(self, raw_invitation_token: str) -> tuple[str, ApplicantPrincipal]:
        token_hash = Invitation.digest_token(raw_invitation_token)
        invitation = self._repository.get_invitation_by_token_hash(token_hash)
        invitation.authorize_token(raw_invitation_token, self._clock.now())
        checked = invitation.mark_token_exchanged(self._clock.now())
        context = TenantContext(
            company_id=checked.company_id,
            actor_type=ActorType.APPLICANT,
            actor_id=checked.applicant_id,
            request_id=self._id_generator.new(),
            trace_id="applicant-token-exchange",
        )
        self._repository.add_invitation(context, checked)
        principal = ApplicantPrincipal(
            company_id=checked.company_id,
            applicant_id=checked.applicant_id,
            invitation_id=checked.invitation_id,
            session_id=self._id_generator.new(),
            issued_at=self._clock.now(),
            expires_at=min(checked.expires_at, self._clock.now() + timedelta(hours=2)),
        )
        raw_session = secrets.token_urlsafe(32)
        self._sessions[_digest(raw_session)] = principal
        return raw_session, principal

    def authenticate(self, raw_session: str | None) -> ApplicantPrincipal:
        if not raw_session:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        principal = self._sessions.get(_digest(raw_session))
        if principal is None:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        if principal.expires_at <= self._clock.now():
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_EXPIRED)
        return principal

    def __repr__(self) -> str:
        return f"ApplicantSessionAdapter(sessions={len(self._sessions)})"


def _digest(value: str) -> str:
    if not value or len(value) > 4_096:
        raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
