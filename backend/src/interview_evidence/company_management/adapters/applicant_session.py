from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from interview_evidence.company_management.domain.hiring import Invitation
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, UUID7Generator
from interview_evidence.shared.security.principals import ApplicantPrincipal
from interview_evidence.shared.tenant import ActorType, TenantContext


class ApplicantSessionAdapter:
    __slots__ = (
        "_clock",
        "_id_generator",
        "_repository",
        "_secret",
        "_sessions",
        "_ttl_seconds",
    )

    def __init__(
        self,
        repository: CompanyManagementRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
        secret: str | None = None,
        ttl_seconds: int = 7_200,
    ) -> None:
        if secret is not None and len(secret) < 16:
            raise ValueError("applicant session secret must contain at least 16 characters")
        if ttl_seconds < 300:
            raise ValueError("applicant session TTL must be at least five minutes")
        self._repository = repository
        self._clock = clock
        self._id_generator = id_generator
        self._secret = secret.encode("utf-8") if secret is not None else None
        self._ttl_seconds = ttl_seconds
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
            expires_at=min(
                checked.expires_at,
                self._clock.now() + timedelta(seconds=self._ttl_seconds),
            ),
        )
        if self._secret is None:
            raw_session = secrets.token_urlsafe(32)
            self._sessions[_digest(raw_session)] = principal
        else:
            raw_session = self._encode(principal)
        return raw_session, principal

    def authenticate(self, raw_session: str | None) -> ApplicantPrincipal:
        if not raw_session:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        if self._secret is not None:
            decoded_principal = self._decode(raw_session)
            if decoded_principal.expires_at <= self._clock.now():
                raise SafeApplicationError(ErrorCode.AUTHENTICATION_EXPIRED)
            return decoded_principal
        principal = self._sessions.get(_digest(raw_session))
        if principal is None:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        if principal.expires_at <= self._clock.now():
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_EXPIRED)
        return principal

    def __repr__(self) -> str:
        mode = "signed" if self._secret is not None else "memory"
        return f"ApplicantSessionAdapter(mode={mode}, sessions={len(self._sessions)})"

    def _encode(self, principal: ApplicantPrincipal) -> str:
        if self._secret is None:
            raise RuntimeError("signed session mode is not configured")
        payload = json.dumps(
            {
                "company_id": str(principal.company_id),
                "applicant_id": str(principal.applicant_id),
                "invitation_id": str(principal.invitation_id),
                "session_id": str(principal.session_id),
                "issued_at": int(principal.issued_at.timestamp()),
                "expires_at": int(principal.expires_at.timestamp()),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.new(self._secret, encoded, hashlib.sha256).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def _decode(self, raw_session: str) -> ApplicantPrincipal:
        if self._secret is None:
            raise RuntimeError("signed session mode is not configured")
        try:
            encoded, signature = raw_session.split(".", 1)
            encoded_bytes = encoded.encode("ascii")
            expected = hmac.new(self._secret, encoded_bytes, hashlib.sha256).digest()
            actual = base64.urlsafe_b64decode(_pad(signature))
            if not hmac.compare_digest(actual, expected):
                raise ValueError("invalid signature")
            payload = json.loads(base64.urlsafe_b64decode(_pad(encoded)).decode("utf-8"))
            return ApplicantPrincipal(
                company_id=payload["company_id"],
                applicant_id=payload["applicant_id"],
                invitation_id=payload["invitation_id"],
                session_id=payload["session_id"],
                issued_at=datetime.fromtimestamp(int(payload["issued_at"]), tz=UTC),
                expires_at=datetime.fromtimestamp(int(payload["expires_at"]), tz=UTC),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED) from None


def _digest(value: str) -> str:
    if not value or len(value) > 4_096:
        raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pad(value: str) -> bytes:
    return (value + "=" * (-len(value) % 4)).encode("ascii")
