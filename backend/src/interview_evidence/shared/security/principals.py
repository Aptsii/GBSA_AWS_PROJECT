"""Company and applicant principals plus deterministic secret-safe authenticators."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext

_ROLE_CODE = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("principal timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _validate_lifetime(issued_at: datetime, expires_at: datetime) -> tuple[datetime, datetime]:
    issued = _as_utc(issued_at)
    expires = _as_utc(expires_at)
    if expires <= issued:
        raise ValueError("expires_at must follow issued_at")
    return issued, expires


@dataclass(frozen=True, slots=True)
class CompanyPrincipal:
    company_id: OpaqueId
    company_user_id: OpaqueId
    identity_subject: str = field(repr=False)
    roles: frozenset[str]
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        issued, expires = _validate_lifetime(self.issued_at, self.expires_at)
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "company_user_id", OpaqueId(self.company_user_id))
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)
        object.__setattr__(self, "roles", frozenset(self.roles))
        if not self.identity_subject or len(self.identity_subject) > 512:
            raise ValueError("identity_subject must be present and bounded")
        if any(not _ROLE_CODE.fullmatch(role) for role in self.roles):
            raise ValueError("roles must contain safe role codes")

    def to_tenant_context(self, *, request_id: str, trace_id: str) -> TenantContext:
        return TenantContext(
            company_id=self.company_id,
            actor_type=ActorType.COMPANY_USER,
            actor_id=self.company_user_id,
            request_id=OpaqueId(request_id),
            trace_id=trace_id,
        )


@dataclass(frozen=True, slots=True)
class ApplicantPrincipal:
    company_id: OpaqueId
    applicant_id: OpaqueId
    invitation_id: OpaqueId
    session_id: OpaqueId
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        issued, expires = _validate_lifetime(self.issued_at, self.expires_at)
        for attribute in ("company_id", "applicant_id", "invitation_id", "session_id"):
            object.__setattr__(self, attribute, OpaqueId(getattr(self, attribute)))
        object.__setattr__(self, "issued_at", issued)
        object.__setattr__(self, "expires_at", expires)

    def to_tenant_context(self, *, request_id: str, trace_id: str) -> TenantContext:
        return TenantContext(
            company_id=self.company_id,
            actor_type=ActorType.APPLICANT,
            actor_id=self.applicant_id,
            request_id=OpaqueId(request_id),
            trace_id=trace_id,
        )

    def applicant_scope(self) -> ApplicantScope:
        return ApplicantScope(
            company_id=self.company_id,
            applicant_id=self.applicant_id,
            invitation_id=self.invitation_id,
        )


@runtime_checkable
class CompanyAuthenticator(Protocol):
    def authenticate(self, credential: str) -> CompanyPrincipal:
        """Validate a credential and return an unexpired company principal."""


@runtime_checkable
class ApplicantAuthenticator(Protocol):
    def authenticate(self, credential: str) -> ApplicantPrincipal:
        """Validate a scoped session credential and return its applicant principal."""


class FakeCompanyAuthenticator:
    __slots__ = ("_clock", "_principals")

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._principals: dict[str, CompanyPrincipal] = {}

    def register(self, credential: str, principal: CompanyPrincipal) -> None:
        self._principals[_credential_digest(credential)] = principal

    def authenticate(self, credential: str) -> CompanyPrincipal:
        principal = self._principals.get(_credential_digest(credential))
        if principal is None:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        if principal.expires_at <= _as_utc(self._clock.now()):
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_EXPIRED)
        return principal

    def __repr__(self) -> str:
        return f"FakeCompanyAuthenticator(entries={len(self._principals)})"


class FakeApplicantAuthenticator:
    __slots__ = ("_clock", "_principals")

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._principals: dict[str, ApplicantPrincipal] = {}

    def register(self, credential: str, principal: ApplicantPrincipal) -> None:
        self._principals[_credential_digest(credential)] = principal

    def authenticate(self, credential: str) -> ApplicantPrincipal:
        principal = self._principals.get(_credential_digest(credential))
        if principal is None:
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
        if principal.expires_at <= _as_utc(self._clock.now()):
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_EXPIRED)
        return principal

    def __repr__(self) -> str:
        return f"FakeApplicantAuthenticator(entries={len(self._principals)})"


def _credential_digest(credential: str) -> str:
    if not credential or len(credential) > 4096:
        raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()
