"""Mandatory tenant and applicant scope primitives."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId

_SAFE_CODE: Final = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ActorType(StrEnum):
    COMPANY_USER = "company_user"
    APPLICANT = "applicant"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class TenantContext:
    company_id: OpaqueId
    actor_type: ActorType
    actor_id: OpaqueId
    request_id: OpaqueId
    trace_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "actor_id", OpaqueId(self.actor_id))
        object.__setattr__(self, "request_id", OpaqueId(self.request_id))
        if not isinstance(self.actor_type, ActorType):
            object.__setattr__(self, "actor_type", ActorType(self.actor_type))
        if not _SAFE_CODE.fullmatch(self.trace_id):
            raise ValueError("trace_id must be a non-empty opaque code")


@dataclass(frozen=True, slots=True)
class EntityRef:
    company_id: OpaqueId
    entity_type: str
    entity_id: OpaqueId
    version: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "entity_id", OpaqueId(self.entity_id))
        if not _SAFE_CODE.fullmatch(self.entity_type):
            raise ValueError("entity_type must be a safe code")
        if self.version is not None and self.version < 1:
            raise ValueError("entity version must be positive")


@dataclass(frozen=True, slots=True)
class ApplicantScope:
    company_id: OpaqueId
    applicant_id: OpaqueId
    invitation_id: OpaqueId

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "applicant_id", OpaqueId(self.applicant_id))
        object.__setattr__(self, "invitation_id", OpaqueId(self.invitation_id))


class TenantContextRequiredError(SafeApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.TENANT_CONTEXT_REQUIRED)


class TenantScopeViolation(SafeApplicationError):
    def __init__(self) -> None:
        super().__init__(ErrorCode.TENANT_SCOPE_DENIED)


def require_tenant_context(context: TenantContext | None) -> TenantContext:
    if not isinstance(context, TenantContext):
        raise TenantContextRequiredError
    return context


def ensure_company_scope(
    context: TenantContext | None,
    company_id: str | OpaqueId,
) -> TenantContext:
    checked = require_tenant_context(context)
    if checked.company_id != OpaqueId(company_id):
        raise TenantScopeViolation
    return checked


def ensure_entity_scope[EntityRefT: EntityRef](
    context: TenantContext | None,
    entity: EntityRefT,
) -> EntityRefT:
    ensure_company_scope(context, entity.company_id)
    return entity


def ensure_applicant_scope[ApplicantScopeT: ApplicantScope](
    context: TenantContext | None,
    scope: ApplicantScopeT,
) -> ApplicantScopeT:
    checked = ensure_company_scope(context, scope.company_id)
    if checked.actor_type is ActorType.APPLICANT and checked.actor_id != scope.applicant_id:
        raise TenantScopeViolation
    return scope
