"""Compare-and-transition state machine for interview sessions."""

from __future__ import annotations

from dataclasses import replace

from interview_evidence.interview_engine.domain.session import InterviewSession, SessionState
from interview_evidence.shared.ids import Clock, SystemClock

_ALLOWED_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.PREPARING: frozenset({SessionState.IN_PROGRESS, SessionState.PAUSED}),
    SessionState.IN_PROGRESS: frozenset(
        {
            SessionState.AWAITING_ANSWER,
            SessionState.PREPARING_QUESTION,
            SessionState.PAUSED,
        }
    ),
    SessionState.AWAITING_ANSWER: frozenset({SessionState.PREPARING_QUESTION, SessionState.PAUSED}),
    SessionState.PREPARING_QUESTION: frozenset({SessionState.AWAITING_ANSWER, SessionState.PAUSED}),
    SessionState.PAUSED: frozenset(
        {
            SessionState.IN_PROGRESS,
            SessionState.AWAITING_ANSWER,
            SessionState.PREPARING_QUESTION,
            SessionState.COMPLETED,
        }
    ),
    SessionState.COMPLETED: frozenset({SessionState.REPORT_GENERATING}),
    SessionState.REPORT_GENERATING: frozenset({SessionState.REVIEWABLE}),
    SessionState.REVIEWABLE: frozenset(),
}


class SessionStateMachine:
    __slots__ = ("_clock",)

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()

    def transition(
        self,
        interview_session: InterviewSession,
        *,
        expected_sequence: int,
        target: SessionState,
    ) -> InterviewSession:
        if interview_session.session_sequence != expected_sequence:
            raise ValueError("stale session sequence")
        checked_target = target if isinstance(target, SessionState) else SessionState(target)
        if checked_target not in _ALLOWED_TRANSITIONS[interview_session.state]:
            raise ValueError("session transition is not allowed")

        now = self._clock.now()
        started_at = interview_session.started_at
        completed_at = interview_session.completed_at
        if checked_target is SessionState.IN_PROGRESS and started_at is None:
            started_at = now
        if checked_target is SessionState.COMPLETED:
            if started_at is None:
                started_at = now
            completed_at = now

        return replace(
            interview_session,
            state=checked_target,
            session_sequence=interview_session.session_sequence + 1,
            row_version=interview_session.row_version + 1,
            started_at=started_at,
            completed_at=completed_at,
        )
