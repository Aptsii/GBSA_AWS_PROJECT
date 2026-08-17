from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope


class DeletionStatus(StrEnum):
    PENDING = "pending"
    RETRYING = "retrying"
    PARTIALLY_COMPLETED = "partially_completed"
    COMPLETED = "completed"


@dataclass(slots=True)
class DeletionTarget:
    target_id: OpaqueId
    store: str
    target_type: str
    owner_lane: str
    status: str = "pending"
    attempts: int = 0
    last_error_code: str | None = None
    verified_at: datetime | None = None

    def __post_init__(self) -> None:
        self.target_id = OpaqueId(self.target_id)


@dataclass(slots=True)
class DeletionManifest:
    manifest_id: OpaqueId
    deletion_request_id: OpaqueId
    targets: list[DeletionTarget]
    status: DeletionStatus = DeletionStatus.PENDING

    def refresh(self) -> None:
        verified = sum(target.status == "verified_absent" for target in self.targets)
        if verified == len(self.targets):
            self.status = DeletionStatus.COMPLETED
        elif verified:
            self.status = DeletionStatus.PARTIALLY_COMPLETED
        elif any(target.attempts for target in self.targets):
            self.status = DeletionStatus.RETRYING


@dataclass(frozen=True, slots=True)
class DeletionRequest:
    deletion_request_id: OpaqueId
    scope: ApplicantScope
    reason: str
    requested_at: datetime
    policy_snapshot: dict[str, object]
