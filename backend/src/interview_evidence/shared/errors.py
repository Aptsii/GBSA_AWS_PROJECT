"""Catalog-backed public errors that never render internal exception text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from interview_evidence.shared.ids import OpaqueId

_FIELD_PATTERN: Final = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    TENANT_CONTEXT_REQUIRED = "TENANT_CONTEXT_REQUIRED"
    TENANT_SCOPE_DENIED = "TENANT_SCOPE_DENIED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    AUTHENTICATION_EXPIRED = "AUTHENTICATION_EXPIRED"
    FORBIDDEN = "FORBIDDEN"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    CONFLICT = "CONFLICT"
    STALE_VERSION = "STALE_VERSION"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    DEPENDENCY_TIMEOUT = "DEPENDENCY_TIMEOUT"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass(frozen=True, slots=True)
class ErrorDefinition:
    title: str
    status: int
    detail: str
    retryable: bool


ERROR_CATALOG = MappingProxyType(
    {
        ErrorCode.INVALID_REQUEST: ErrorDefinition(
            "Invalid request", 400, "The request did not satisfy the required contract.", False
        ),
        ErrorCode.TENANT_CONTEXT_REQUIRED: ErrorDefinition(
            "Tenant context required", 400, "A valid tenant context is required.", False
        ),
        ErrorCode.TENANT_SCOPE_DENIED: ErrorDefinition(
            "Tenant scope denied",
            403,
            "The requested resource is outside the allowed scope.",
            False,
        ),
        ErrorCode.AUTHENTICATION_REQUIRED: ErrorDefinition(
            "Authentication required", 401, "Valid authentication is required.", False
        ),
        ErrorCode.AUTHENTICATION_EXPIRED: ErrorDefinition(
            "Authentication expired", 401, "The authentication session has expired.", False
        ),
        ErrorCode.FORBIDDEN: ErrorDefinition(
            "Operation forbidden", 403, "The principal cannot perform this operation.", False
        ),
        ErrorCode.RESOURCE_NOT_FOUND: ErrorDefinition(
            "Resource not found", 404, "The requested resource was not found.", False
        ),
        ErrorCode.CONFLICT: ErrorDefinition(
            "State conflict", 409, "The request conflicts with current durable state.", False
        ),
        ErrorCode.STALE_VERSION: ErrorDefinition(
            "Stale version", 409, "The supplied version is no longer current.", False
        ),
        ErrorCode.IDEMPOTENCY_CONFLICT: ErrorDefinition(
            "Idempotency conflict",
            409,
            "The idempotency key was already used for a different operation.",
            False,
        ),
        ErrorCode.RATE_LIMITED: ErrorDefinition(
            "Rate limited", 429, "The operation was rate limited.", True
        ),
        ErrorCode.DEPENDENCY_TIMEOUT: ErrorDefinition(
            "Dependency timed out", 503, "A required service did not respond in time.", True
        ),
        ErrorCode.DEPENDENCY_UNAVAILABLE: ErrorDefinition(
            "Dependency unavailable", 503, "A required service is temporarily unavailable.", True
        ),
        ErrorCode.INTERNAL_ERROR: ErrorDefinition(
            "Internal error", 500, "The operation could not be completed.", False
        ),
    }
)


@dataclass(frozen=True, slots=True)
class FieldError:
    field: str
    code: str

    def __post_init__(self) -> None:
        if not _FIELD_PATTERN.fullmatch(self.field):
            raise ValueError("field must be a safe dotted field path")
        if not _FIELD_PATTERN.fullmatch(self.code):
            raise ValueError("field error code must be a safe code")

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "code": self.code}


@dataclass(frozen=True, slots=True)
class ErrorEnvelope:
    type: str
    title: str
    status: int
    code: ErrorCode
    detail: str
    request_id: OpaqueId
    retryable: bool
    current_version: int | None = None
    errors: tuple[FieldError, ...] = ()

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "code": self.code.value,
            "detail": self.detail,
            "request_id": str(self.request_id),
            "retryable": self.retryable,
        }
        if self.current_version is not None:
            result["current_version"] = self.current_version
        if self.errors:
            result["errors"] = [error.to_dict() for error in self.errors]
        return result


class SafeApplicationError(Exception):
    """An operationally safe exception identified only by a catalog code."""

    __slots__ = ("code", "current_version", "field_errors")

    def __init__(
        self,
        code: ErrorCode,
        *,
        current_version: int | None = None,
        field_errors: tuple[FieldError, ...] = (),
        cause: BaseException | None = None,
    ) -> None:
        del cause  # Never retain potentially sensitive exception text.
        if current_version is not None and current_version < 1:
            raise ValueError("current_version must be positive")
        self.code = code
        self.current_version = current_version
        self.field_errors = field_errors
        super().__init__(code.value)

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code.value!r})"

    def to_envelope(self, request_id: str | OpaqueId) -> ErrorEnvelope:
        return build_error_envelope(
            self.code,
            request_id=request_id,
            current_version=self.current_version,
            field_errors=self.field_errors,
        )


def build_error_envelope(
    code: ErrorCode,
    *,
    request_id: str | OpaqueId,
    current_version: int | None = None,
    field_errors: tuple[FieldError, ...] = (),
) -> ErrorEnvelope:
    definition = ERROR_CATALOG[code]
    if current_version is not None and current_version < 1:
        raise ValueError("current_version must be positive")
    slug = code.value.lower().replace("_", "-")
    return ErrorEnvelope(
        type=f"urn:interview-evidence:error:{slug}",
        title=definition.title,
        status=definition.status,
        code=code,
        detail=definition.detail,
        request_id=OpaqueId(request_id),
        retryable=definition.retryable,
        current_version=current_version,
        errors=field_errors,
    )
