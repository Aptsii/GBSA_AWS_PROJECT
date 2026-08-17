from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from interview_evidence.shared.ids import OpaqueId


class AssessmentState(StrEnum):
    CONFIRMED = "confirmed"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEEDS_FOLLOW_UP = "needs_follow_up"


class Sufficiency(StrEnum):
    DIRECT = "direct"
    SUPPORTING = "supporting"
    WEAK = "weak"


@dataclass(frozen=True, slots=True)
class Evidence:
    evidence_id: OpaqueId
    company_id: OpaqueId
    report_item_id: OpaqueId
    criterion_id: OpaqueId
    competency_model_version_id: OpaqueId
    answer_turn_id: OpaqueId
    transcript_segment_id: OpaqueId
    video_start_ms: int
    video_end_ms: int
    observation: str
    rationale: str
    sufficiency: Sufficiency
    generation_version: str
    created_at: datetime

    def __post_init__(self) -> None:
        for field in (
            "evidence_id",
            "company_id",
            "report_item_id",
            "criterion_id",
            "competency_model_version_id",
            "answer_turn_id",
            "transcript_segment_id",
        ):
            object.__setattr__(self, field, OpaqueId(getattr(self, field)))
        if not isinstance(self.sufficiency, Sufficiency):
            object.__setattr__(self, "sufficiency", Sufficiency(self.sufficiency))
        if self.video_start_ms < 0 or self.video_end_ms <= self.video_start_ms:
            raise ValueError("Evidence video range is invalid")
        if not all(
            value.strip() for value in (self.observation, self.rationale, self.generation_version)
        ):
            raise ValueError("Evidence narrative and provenance are required")
        object.__setattr__(self, "created_at", _utc(self.created_at))


@dataclass(frozen=True, slots=True)
class ReportItem:
    report_item_id: OpaqueId
    report_id: OpaqueId
    criterion_id: OpaqueId
    competency_model_version_id: OpaqueId
    assessment_state: AssessmentState
    observation: str
    rationale: str
    uncertainty: str
    evidence: tuple[Evidence, ...] = ()
    follow_up_question: str | None = None

    def __post_init__(self) -> None:
        for field in ("report_item_id", "report_id", "criterion_id", "competency_model_version_id"):
            object.__setattr__(self, field, OpaqueId(getattr(self, field)))
        if not isinstance(self.assessment_state, AssessmentState):
            object.__setattr__(self, "assessment_state", AssessmentState(self.assessment_state))
        if (
            self.assessment_state
            in {AssessmentState.CONFIRMED, AssessmentState.PARTIALLY_CONFIRMED}
            and not self.evidence
        ):
            raise ValueError("confirmed ReportItem requires Evidence")
        for item in self.evidence:
            if (
                item.report_item_id != self.report_item_id
                or item.criterion_id != self.criterion_id
                or item.competency_model_version_id != self.competency_model_version_id
            ):
                raise ValueError("Evidence axis does not match ReportItem")


@dataclass(frozen=True, slots=True)
class Report:
    report_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    competency_model_version_id: OpaqueId
    report_version: int
    status: str
    summary: str
    model_config_version: str
    prompt_version: str
    items: tuple[ReportItem, ...]
    created_at: datetime
    kind: str = "ai_original"

    def __post_init__(self) -> None:
        for field in (
            "report_id",
            "company_id",
            "interview_session_id",
            "competency_model_version_id",
        ):
            object.__setattr__(self, field, OpaqueId(getattr(self, field)))
        if self.report_version < 1 or self.kind != "ai_original":
            raise ValueError("report version or immutable kind is invalid")
        object.__setattr__(self, "created_at", _utc(self.created_at))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)
