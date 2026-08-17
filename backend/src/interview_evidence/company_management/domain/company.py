from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from interview_evidence.shared._validation import utc_instant
from interview_evidence.shared.ids import OpaqueId


def _required_text(value: str, *, field_name: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must contain between 1 and {maximum} characters")
    return normalized


class CompanyStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class CompanyUserStatus(StrEnum):
    INVITED = "invited"
    ACTIVE = "active"
    DISABLED = "disabled"


class PositionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class Company:
    company_id: OpaqueId
    name: str
    created_at: datetime
    status: CompanyStatus = CompanyStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "name", _required_text(self.name, field_name="name", maximum=200))
        object.__setattr__(self, "created_at", utc_instant(self.created_at))
        if not isinstance(self.status, CompanyStatus):
            object.__setattr__(self, "status", CompanyStatus(self.status))


@dataclass(frozen=True, slots=True)
class CompanyUser:
    company_user_id: OpaqueId
    company_id: OpaqueId
    identity_subject: str
    email: str
    roles: frozenset[str]
    status: CompanyUserStatus = CompanyUserStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_user_id", OpaqueId(self.company_user_id))
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(
            self,
            "identity_subject",
            _required_text(self.identity_subject, field_name="identity_subject", maximum=255),
        )
        normalized_email = self.email.strip().lower()
        if "@" not in normalized_email or len(normalized_email) > 320:
            raise ValueError("email must be a valid normalized address")
        object.__setattr__(self, "email", normalized_email)
        object.__setattr__(self, "roles", frozenset(self.roles))
        if not isinstance(self.status, CompanyUserStatus):
            object.__setattr__(self, "status", CompanyUserStatus(self.status))


@dataclass(frozen=True, slots=True)
class Position:
    position_id: OpaqueId
    company_id: OpaqueId
    title: str
    description: str
    created_by: OpaqueId
    created_at: datetime
    status: PositionStatus = PositionStatus.DRAFT
    row_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "position_id", OpaqueId(self.position_id))
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "created_by", OpaqueId(self.created_by))
        object.__setattr__(
            self, "title", _required_text(self.title, field_name="title", maximum=200)
        )
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, field_name="description", maximum=20_000),
        )
        object.__setattr__(self, "created_at", utc_instant(self.created_at))
        if not isinstance(self.status, PositionStatus):
            object.__setattr__(self, "status", PositionStatus(self.status))
        if self.row_version < 1:
            raise ValueError("row_version must be positive")

    def to_view(self) -> dict[str, object]:
        return {
            "position_id": str(self.position_id),
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "row_version": self.row_version,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
        }
