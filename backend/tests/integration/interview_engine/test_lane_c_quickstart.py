from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.interview_engine.adapters.polly import SpeechSynthesizer
from interview_evidence.interview_engine.adapters.retrieval_client import RetrievalClient
from interview_evidence.interview_engine.application.interview_service import InterviewService
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    CRITERION_ID,
    INVITATION_ID,
    MODEL_ID,
    STRATEGY_ID,
    make_tenant_context,
)


class _UnavailableRetrieval:
    def retrieve_context(self, *_: object, **__: object) -> dict[str, object]:
        raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE)


def test_lane_c_quickstart_survives_reconnect_without_duplicate_turns() -> None:
    clock = FixedClock(datetime(2026, 8, 17, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x41" * size)
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    service = InterviewService(
        retrieval=RetrievalClient(_UnavailableRetrieval()),
        speech=SpeechSynthesizer(fail=True, clock=clock, id_generator=ids),
        clock=clock,
        id_generator=ids,
    )

    created = service.create_session(
        context,
        scope,
        interview_strategy_id=STRATEGY_ID,
        competency_model_version_id=MODEL_ID,
        idempotency_key="lane-c-session-create-0001",
    )
    started = service.start(
        context,
        scope,
        created.session.interview_session_id,
        expected_sequence=0,
    )
    arguments = {
        "expected_sequence": started.session_sequence,
        "answer_turn_id": "018f2000-0000-7000-8000-000000000233",
        "transcript_text": "장애 시 durable checkpoint를 기준으로 복구했습니다.",
        "transcript_confidence": 0.91,
        "criterion_id": CRITERION_ID,
        "criterion_name": "문제 해결",
        "remaining_criteria": ({"criterion_id": CRITERION_ID, "name": "문제 해결"},),
        "idempotency_key": "lane-c-answer-complete-0001",
        "last_recording_chunk_sequence": 0,
    }
    first = service.finalize_answer(
        context,
        scope,
        created.session.interview_session_id,
        **arguments,
    )
    replay = service.finalize_answer(
        context,
        scope,
        created.session.interview_session_id,
        **arguments,
    )

    assert replay == first
    assert len(service.list_turns(context, scope, created.session.interview_session_id)) == 2
    assert first.answer_turn.evidence_eligible is True
    assert first.speech.text_only is True
    assert set(first.session.degraded_modes) == {"search_fallback", "text_only"}
    assert not hasattr(first, "assessment")

    snapshot = service.resume(
        context,
        scope,
        created.session.interview_session_id,
        client_sequence=1,
    )
    assert snapshot.stale_client is True
    assert snapshot.server_sequence == first.session.session_sequence
    assert snapshot.last_final_turn_id == first.answer_turn.turn_id
