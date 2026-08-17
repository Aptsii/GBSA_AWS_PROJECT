from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Literal

from interview_evidence.shared.ids import OpaqueId


class StrategyStatus(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class SourceReferenceCandidate:
    source_type: Literal["submission_chunk", "candidate_code_unit"]
    source_id: OpaqueId
    locator_version: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", OpaqueId(self.source_id))
        if self.locator_version < 1:
            raise ValueError("locator version must be positive")


@dataclass(frozen=True, slots=True)
class InterviewStrategy:
    interview_strategy_id: OpaqueId
    company_id: OpaqueId
    invitation_id: OpaqueId
    competency_model_version_id: OpaqueId
    strategy_version: int
    common_topics: tuple[dict[str, object], ...]
    verification_points: tuple[dict[str, object], ...]
    follow_up_directions: dict[str, object]
    time_budget: dict[str, object]
    required_evidence_plan: dict[str, object]
    source_reference_candidates: tuple[SourceReferenceCandidate, ...]
    model_config_version: str
    status: StrategyStatus
    created_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "interview_strategy_id",
            "company_id",
            "invitation_id",
            "competency_model_version_id",
        ):
            object.__setattr__(self, name, OpaqueId(getattr(self, name)))
        if self.strategy_version < 1:
            raise ValueError("strategy version must be positive")
        if not isinstance(self.status, StrategyStatus):
            object.__setattr__(self, "status", StrategyStatus(self.status))

    def snapshot(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "invitation_id": str(self.invitation_id),
            "interview_strategy_id": str(self.interview_strategy_id),
            "strategy_version": self.strategy_version,
            "competency_model_version_id": str(self.competency_model_version_id),
            "status": self.status.value,
            "common_topics": list(self.common_topics),
            "verification_points": list(self.verification_points),
            "follow_up_directions": self.follow_up_directions,
            "time_budget": self.time_budget,
            "required_evidence_plan": self.required_evidence_plan,
            "source_reference_candidates": [
                {
                    "source_type": candidate.source_type,
                    "source_id": str(candidate.source_id),
                    "locator_version": candidate.locator_version,
                }
                for candidate in self.source_reference_candidates
            ],
            "model_config_version": self.model_config_version,
        }
