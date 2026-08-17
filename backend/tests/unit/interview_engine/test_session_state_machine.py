from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interview_evidence.interview_engine.application.state_machine import SessionStateMachine
from interview_evidence.interview_engine.domain.session import InterviewSession, SessionState
from interview_evidence.shared.tenant import ApplicantScope

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    MODEL_ID,
    STRATEGY_ID,
)


def _session() -> InterviewSession:
    return InterviewSession(
        interview_session_id="018f2000-0000-7000-8000-000000000230",
        scope=ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID),
        interview_strategy_id=STRATEGY_ID,
        competency_model_version_id=MODEL_ID,
        state=SessionState.PREPARING,
        session_sequence=0,
        row_version=1,
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def test_compare_and_transition_increments_sequence_and_version() -> None:
    changed = SessionStateMachine().transition(
        _session(), expected_sequence=0, target=SessionState.IN_PROGRESS
    )
    assert changed.state == "in_progress"
    assert changed.session_sequence == 1
    assert changed.row_version == 2


def test_state_machine_rejects_stale_and_forbidden_transitions() -> None:
    with pytest.raises(ValueError, match="stale"):
        SessionStateMachine().transition(
            _session(), expected_sequence=1, target=SessionState.IN_PROGRESS
        )
    with pytest.raises(ValueError, match="transition"):
        SessionStateMachine().transition(
            _session(), expected_sequence=0, target=SessionState.COMPLETED
        )
