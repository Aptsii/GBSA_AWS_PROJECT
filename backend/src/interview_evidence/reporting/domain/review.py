from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from interview_evidence.shared.ids import OpaqueId


class ReviewType(StrEnum):
    ASSESSMENT_OVERRIDE = "assessment_override"
    NOTE = "note"
    BOOKMARK = "bookmark"
    FINAL_DECISION = "final_decision"


@dataclass(frozen=True, slots=True)
class HumanReview:
    human_review_id: OpaqueId
    company_id: OpaqueId
    report_id: OpaqueId
    company_user_id: OpaqueId
    review_type: ReviewType
    target_id: OpaqueId
    value: dict[str, object]
    reason: str | None
    created_at: datetime

    def __post_init__(self) -> None:
        for field in ("human_review_id", "company_id", "report_id", "company_user_id", "target_id"):
            object.__setattr__(self, field, OpaqueId(getattr(self, field)))
        if not isinstance(self.review_type, ReviewType):
            object.__setattr__(self, "review_type", ReviewType(self.review_type))
        if (
            self.review_type in {ReviewType.ASSESSMENT_OVERRIDE, ReviewType.FINAL_DECISION}
            and not self.reason
        ):
            raise ValueError("override and final decision require reason")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        object.__setattr__(self, "created_at", self.created_at.astimezone(UTC))
