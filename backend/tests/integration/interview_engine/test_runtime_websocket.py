from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID

import pytest
from interview_evidence.interview_engine.api.runtime import (
    SQLAlchemyInterviewRouteService,
    SQLAlchemyInterviewStreamHandler,
)
from interview_evidence.interview_engine.api.websocket import ProtocolMessage
from interview_evidence.interview_engine.domain.turn import TurnSpeaker, TurnStatus
from interview_evidence.interview_engine.repositories.postgres import (
    InterviewSessionRepository,
)
from interview_evidence.shared.aws_clients.ports import (
    FakeObjectStorage,
    FakeSpeechClient,
    ProtectedBytes,
    ProtectedText,
    TranscriptionResult,
)
from interview_evidence.shared.database import Base
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    CRITERION_ID,
    INVITATION_ID,
    STRATEGY_ID,
    make_tenant_context,
)

FIRST_TRANSCRIPTION_ID = "018f2000-0000-7000-8000-000000000402"
SECOND_TRANSCRIPTION_ID = "018f2000-0000-7000-8000-000000000403"


@pytest.mark.asyncio
async def test_text_answer_uses_persisted_strategy_question_and_criterion_axis() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    clock = FixedClock(datetime(2026, 8, 18, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x53" * size)
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    strategy = {
        "company_id": str(COMPANY_ID),
        "invitation_id": str(INVITATION_ID),
        "interview_strategy_id": str(STRATEGY_ID),
        "strategy_version": 1,
        "competency_model_version_id": "018f2000-0000-7000-8000-000000000202",
        "status": "ready",
        "common_topics": [
            {
                "criterion_id": str(CRITERION_ID),
                "common_questions": ["장애 복구 전략을 어떻게 검증했나요?"],
            }
        ],
        "verification_points": [
            {
                "criterion_id": str(CRITERION_ID),
                "prompt": "제출 자료의 장애 복구 설계에서 본인이 내린 판단을 설명해 주세요.",
                "source_reference_ids": ["018f2000-0000-7000-8000-000000000222"],
            }
        ],
        "follow_up_directions": {"max_per_topic": 2},
        "time_budget": {"minutes": 30},
        "required_evidence_plan": {"required_criteria": 1},
        "source_reference_candidates": [],
        "model_config_version": "strategy-model-v1",
    }

    def strategy_provider(
        _context: TenantContext,
        *,
        strategy_id: str,
    ) -> dict[str, object]:
        assert strategy_id == str(STRATEGY_ID)
        return strategy

    with Session(engine) as database:
        repository = InterviewSessionRepository(database)
        route_service = SQLAlchemyInterviewRouteService(
            repository,
            clock=clock,
            id_generator=ids,
            object_storage=FakeObjectStorage(),
            strategy_provider=strategy_provider,
        )
        handler = SQLAlchemyInterviewStreamHandler(
            repository,
            route_service,
            clock=clock,
            id_generator=ids,
            max_questions=1,
        )
        created = route_service.create_interview_session(
            context=context,
            scope=scope,
            equipment_check_id="018f2000-0000-7000-8000-000000000201",
            strategy_id=STRATEGY_ID,
            acknowledged_partial_analysis=False,
            idempotency_key="runtime-text-session-0001",
        )
        session_id = str(created["interview_session_id"])

        started = await handler.handle_message(
            context,
            scope,
            _message(session_id, 0, "session.start", {"equipment_check_id": "check-1"}),
        )
        assert isinstance(started, tuple)
        question = started[-1]
        assert question.message_type == "question.ready"
        assert question.payload["text"] == strategy["verification_points"][0]["prompt"]
        assert question.payload["target_criterion_id"] == str(CRITERION_ID)
        assert question.payload["source_reference_count"] == 1

        answer_turn_id = "018f2000-0000-7000-8000-000000000406"
        transcript = await handler.handle_message(
            context,
            scope,
            _message(
                session_id,
                2,
                "answer.text.submit",
                {
                    "answer_turn_id": answer_turn_id,
                    "text": "복구 목표를 수치로 정의하고 장애 주입으로 검증했습니다.",
                },
            ),
        )
        assert isinstance(transcript, ProtocolMessage)
        assert transcript.message_type == "transcript.final"
        assert transcript.payload["text"] == (
            "복구 목표를 수치로 정의하고 장애 주입으로 검증했습니다."
        )

        completed = await handler.handle_message(
            context,
            scope,
            _message(
                session_id,
                2,
                "answer.complete",
                {
                    "answer_turn_id": answer_turn_id,
                    "last_audio_chunk_sequence": 0,
                    "last_recording_chunk_sequence": 0,
                },
            ),
        )
        assert isinstance(completed, tuple)
        assert completed[-1].message_type == "session.completed"
        final_answer = repository.list_turns(context, scope, session_id)[-1]
        assert final_answer.speaker is TurnSpeaker.APPLICANT
        assert final_answer.status is TurnStatus.FINAL
        assert final_answer.text is not None
        assert final_answer.text.reveal().startswith("복구 목표")
    engine.dispose()


@pytest.mark.asyncio
async def test_sql_websocket_runs_transcript_multiple_questions_completion_and_resume() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    clock = FixedClock(datetime(2026, 8, 18, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x51" * size)
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    speech = FakeSpeechClient(
        transcriptions={
            FIRST_TRANSCRIPTION_ID: TranscriptionResult(
                text=ProtectedText("첫 번째 답변에서 복구 절차와 결과를 설명했습니다."),
                confidence=0.94,
                review_required=False,
            ),
            SECOND_TRANSCRIPTION_ID: TranscriptionResult(
                text=ProtectedText("두 번째 답변에서 본인의 판단과 측정 결과를 보완했습니다."),
                confidence=0.88,
                review_required=False,
            ),
        },
        syntheses={},
    )
    first_audio = ProtectedBytes(b"first-answer-audio")
    second_audio = ProtectedBytes(b"second-answer-audio")
    with Session(engine) as database:
        repository = InterviewSessionRepository(database)
        route_service = SQLAlchemyInterviewRouteService(
            repository,
            clock=clock,
            id_generator=ids,
            object_storage=FakeObjectStorage(),
        )
        handler = SQLAlchemyInterviewStreamHandler(
            repository,
            route_service,
            clock=clock,
            id_generator=ids,
            transcriber=speech,
            max_questions=2,
        )
        created = route_service.create_interview_session(
            context=context,
            scope=scope,
            equipment_check_id="018f2000-0000-7000-8000-000000000201",
            strategy_id=STRATEGY_ID,
            acknowledged_partial_analysis=False,
            idempotency_key="runtime-session-create-0001",
        )
        session_id = str(created["interview_session_id"])

        started = await handler.handle_message(
            context,
            scope,
            _message(session_id, 0, "session.start", {"equipment_check_id": "check-1"}),
        )
        assert isinstance(started, tuple)
        assert [item.message_type for item in started] == [
            "session.state_changed",
            "question.ready",
        ]

        first_answer_turn_id = "018f2000-0000-7000-8000-000000000401"
        first_transcript = await handler.handle_binary(
            context,
            scope,
            _audio_message(
                session_id,
                2,
                first_answer_turn_id,
                first_audio,
                correlation_id=FIRST_TRANSCRIPTION_ID,
            ),
            first_audio,
        )
        assert isinstance(first_transcript, ProtocolMessage)
        assert first_transcript.message_type == "transcript.final"
        assert first_transcript.payload["answer_turn_id"] == first_answer_turn_id

        next_question = await handler.handle_message(
            context,
            scope,
            _message(
                session_id,
                2,
                "answer.complete",
                {
                    "answer_turn_id": first_answer_turn_id,
                    "last_audio_chunk_sequence": 1,
                    "last_recording_chunk_sequence": 0,
                },
            ),
        )
        assert isinstance(next_question, tuple)
        assert [item.message_type for item in next_question] == [
            "session.state_changed",
            "question.preparing",
            "question.ready",
        ]
        assert next_question[-1].payload["text"] != started[-1].payload["text"]

        resumed = await handler.handle_message(
            context,
            scope,
            _message(session_id, 4, "session.resume", {}),
        )
        assert isinstance(resumed, tuple)
        assert [item.message_type for item in resumed] == [
            "resume.snapshot",
            "question.ready",
        ]
        assert resumed[-1].payload == next_question[-1].payload

        second_answer_turn_id = "018f2000-0000-7000-8000-000000000404"
        second_transcript = await handler.handle_binary(
            context,
            scope,
            _audio_message(
                session_id,
                4,
                second_answer_turn_id,
                second_audio,
                correlation_id=SECOND_TRANSCRIPTION_ID,
            ),
            second_audio,
        )
        assert isinstance(second_transcript, ProtocolMessage)
        assert second_transcript.message_type == "transcript.final"

        completed = await handler.handle_message(
            context,
            scope,
            _message(
                session_id,
                4,
                "answer.complete",
                {
                    "answer_turn_id": second_answer_turn_id,
                    "last_audio_chunk_sequence": 1,
                    "last_recording_chunk_sequence": 0,
                },
            ),
        )
        assert isinstance(completed, tuple)
        assert completed[-1].message_type == "session.completed"
        assert repository.get_session(context, scope, session_id).state.value == "completed"
        turns = repository.list_turns(context, scope, session_id)
        assert len(turns) == 4
        assert [turn.speaker for turn in turns] == [
            TurnSpeaker.INTERVIEWER,
            TurnSpeaker.APPLICANT,
            TurnSpeaker.INTERVIEWER,
            TurnSpeaker.APPLICANT,
        ]
        assert all(
            turn.status is TurnStatus.FINAL
            for turn in turns
            if turn.speaker is TurnSpeaker.APPLICANT
        )

        stale_replay = await handler.handle_message(
            context,
            scope,
            _message(
                session_id,
                2,
                "answer.complete",
                {
                    "answer_turn_id": first_answer_turn_id,
                    "last_audio_chunk_sequence": 1,
                    "last_recording_chunk_sequence": 0,
                },
            ),
        )
        assert isinstance(stale_replay, ProtocolMessage)
        assert stale_replay.message_type == "resume.snapshot"
        assert len(repository.list_turns(context, scope, session_id)) == 4

        resumed = await handler.handle_message(
            context,
            scope,
            _message(session_id, 0, "session.resume", {}),
        )
        assert isinstance(resumed, ProtocolMessage)
        assert resumed.message_type == "resume.snapshot"
        assert resumed.payload["state"] == "completed"
        assert resumed.payload["last_final_turn_id"] == second_answer_turn_id
    engine.dispose()


@pytest.mark.asyncio
async def test_sql_websocket_pauses_safely_when_transcription_is_unavailable_then_resumes() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    clock = FixedClock(datetime(2026, 8, 18, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x52" * size)
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    audio = ProtectedBytes(b"unavailable-transcription")

    with Session(engine) as database:
        repository = InterviewSessionRepository(database)
        route_service = SQLAlchemyInterviewRouteService(
            repository,
            clock=clock,
            id_generator=ids,
            object_storage=FakeObjectStorage(),
        )
        handler = SQLAlchemyInterviewStreamHandler(
            repository,
            route_service,
            clock=clock,
            id_generator=ids,
        )
        created = route_service.create_interview_session(
            context=context,
            scope=scope,
            equipment_check_id="018f2000-0000-7000-8000-000000000201",
            strategy_id=STRATEGY_ID,
            acknowledged_partial_analysis=False,
            idempotency_key="runtime-pause-session-0001",
        )
        session_id = str(created["interview_session_id"])
        await handler.handle_message(
            context,
            scope,
            _message(session_id, 0, "session.start", {"equipment_check_id": "check-1"}),
        )

        paused = await handler.handle_binary(
            context,
            scope,
            _audio_message(
                session_id,
                2,
                "018f2000-0000-7000-8000-000000000405",
                audio,
                correlation_id=FIRST_TRANSCRIPTION_ID,
            ),
            audio,
        )
        assert isinstance(paused, ProtocolMessage)
        assert paused.message_type == "session.paused"
        assert paused.payload["reason_code"] == "transcription_unavailable"
        assert repository.get_session(context, scope, session_id).state.value == "paused"
        assert all(
            turn.speaker is TurnSpeaker.INTERVIEWER
            for turn in repository.list_turns(context, scope, session_id)
        )

        resumed = await handler.handle_message(
            context,
            scope,
            _message(session_id, 3, "session.resume", {}),
        )
        assert isinstance(resumed, tuple)
        assert [item.message_type for item in resumed] == [
            "resume.snapshot",
            "question.ready",
        ]
        assert resumed[0].payload["state"] == "awaiting_answer"
        assert "audio.chunk.begin" in resumed[0].payload["allowed_client_messages"]
    engine.dispose()


def _audio_message(
    session_id: str,
    sequence: int,
    answer_turn_id: str,
    content: ProtectedBytes,
    *,
    correlation_id: str,
) -> ProtocolMessage:
    raw = content.reveal()
    return _message(
        session_id,
        sequence,
        "audio.chunk.begin",
        {
            "answer_turn_id": answer_turn_id,
            "chunk_sequence": 1,
            "codec": "pcm_s16le",
            "sample_rate_hz": 16_000,
            "channel_count": 1,
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "session_start_ms": 0,
            "session_end_ms": 1_000,
        },
        correlation_id=correlation_id,
    )


def _message(
    session_id: str,
    sequence: int,
    message_type: str,
    payload: dict[str, object],
    *,
    correlation_id: str = FIRST_TRANSCRIPTION_ID,
) -> ProtocolMessage:
    return ProtocolMessage(
        protocol_version="1.0",
        message_type=message_type,
        session_id=UUID(session_id),
        sequence=sequence,
        idempotency_key=f"runtime-{message_type}-0001",
        correlation_id=UUID(correlation_id),
        sent_at=datetime(2026, 8, 18, tzinfo=UTC),
        payload=payload,
    )
