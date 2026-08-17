"""Interview session state and invariants."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope


class SessionState(StrEnum):
    PREPARING = "preparing"
    IN_PROGRESS = "in_progress"
    AWAITING_ANSWER = "awaiting_answer"
    PREPARING_QUESTION = "preparing_question"
    PAUSED = "paused"
    COMPLETED = "completed"
    REPORT_GENERATING = "report_generating"
    REVIEWABLE = "reviewable"


_COMPLETED_STATES = frozenset(
    {SessionState.COMPLETED, SessionState.REPORT_GENERATING, SessionState.REVIEWABLE}
)


@dataclass(frozen=True, slots=True)
class InterviewSession:
    interview_session_id: OpaqueId
    scope: ApplicantScope
    interview_strategy_id: OpaqueId
    competency_model_version_id: OpaqueId
    state: SessionState
    session_sequence: int
    row_version: int
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    degraded_modes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "interview_session_id", OpaqueId(self.interview_session_id))
        object.__setattr__(self, "interview_strategy_id", OpaqueId(self.interview_strategy_id))
        object.__setattr__(
            self,
            "competency_model_version_id",
            OpaqueId(self.competency_model_version_id),
        )
        if not isinstance(self.scope, ApplicantScope):
            raise TypeError("scope must be an ApplicantScope")
        if not isinstance(self.state, SessionState):
            object.__setattr__(self, "state", SessionState(self.state))
        if self.session_sequence < 0:
            raise ValueError("session_sequence must be nonnegative")
        if self.row_version < 1:
            raise ValueError("row_version must be positive")
        object.__setattr__(self, "created_at", _utc(self.created_at))
        if self.started_at is not None:
            object.__setattr__(self, "started_at", _utc(self.started_at))
        if self.completed_at is not None:
            object.__setattr__(self, "completed_at", _utc(self.completed_at))
        if self.completed_at is not None and self.started_at is None:
            raise ValueError("completed sessions require started_at")
        if self.state in _COMPLETED_STATES and self.completed_at is None:
            raise ValueError("completed session states require completed_at")
        if self.state not in _COMPLETED_STATES and self.completed_at is not None:
            raise ValueError("active session states cannot have completed_at")
        if len(self.degraded_modes) != len(set(self.degraded_modes)):
            raise ValueError("degraded_modes must not contain duplicates")
        if any(
            not mode or any(character.isspace() for character in mode)
            for mode in self.degraded_modes
        ):
            raise ValueError("degraded_modes must contain safe non-empty codes")

    @property
    def company_id(self) -> OpaqueId:
        return self.scope.company_id

    def with_degraded_mode(self, mode: str) -> InterviewSession:
        if mode in self.degraded_modes:
            return self
        return replace(self, degraded_modes=(*self.degraded_modes, mode))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("session timestamps must be timezone-aware")
    return value.astimezone(UTC)
