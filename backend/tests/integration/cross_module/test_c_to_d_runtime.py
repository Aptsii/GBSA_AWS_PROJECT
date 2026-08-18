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
from interview_evidence.interview_engine.contracts import InterviewEvidencePublicService
from interview_evidence.interview_engine.domain.turn import RecordingChunk, UploadStatus
from interview_evidence.interview_engine.repositories.postgres import InterviewSessionRepository
from interview_evidence.reporting.api.runtime import SQLAlchemyReportingRouteService
from interview_evidence.shared.aws_clients.ports import FakeObjectStorage
from interview_evidence.shared.database import Base
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext
from interview_evidence.workers.reporting.runtime import SQLAlchemyReportingCompletionHandler
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    STRATEGY_ID,
    make_tenant_context,
)


@pytest.mark.asyncio
async def test_completed_session_event_persists_report_timeline_media_and_evidence() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    clock = FixedClock(datetime(2026, 8, 18, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x61" * size)
    applicant_context = TenantContext(**make_tenant_context())
    company_context = TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.COMPANY_USER,
        actor_id="018f2000-0000-7000-8000-000000000111",
        request_id="018f2000-0000-7000-8000-000000000112",
        trace_id="reporting-runtime-test",
    )
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)

    with Session(engine) as database:
        repository = InterviewSessionRepository(database)
        public = InterviewEvidencePublicService(repository)
        completion_handler = SQLAlchemyReportingCompletionHandler(
            database,
            interview_public=public,
            clock=clock,
            id_generator=ids,
        )
        route_service = SQLAlchemyInterviewRouteService(
            repository,
            clock=clock,
            id_generator=ids,
            object_storage=FakeObjectStorage(),
        )
        stream = SQLAlchemyInterviewStreamHandler(
            repository,
            route_service,
            clock=clock,
            id_generator=ids,
            max_questions=1,
            completion_handler=completion_handler,
        )
        created = route_service.create_interview_session(
            context=applicant_context,
            scope=scope,
            equipment_check_id="018f2000-0000-7000-8000-000000000201",
            strategy_id=STRATEGY_ID,
            acknowledged_partial_analysis=False,
            idempotency_key="reporting-runtime-session-0001",
        )
        session_id = str(created["interview_session_id"])
        started = await stream.handle_message(
            applicant_context,
            scope,
            _message(session_id, 0, "session.start", {"equipment_check_id": "check-1"}),
        )
        assert isinstance(started, tuple)

        media = b"verified-applicant-answer"
        repository.add_recording_chunk(
            applicant_context,
            scope,
            RecordingChunk(
                recording_chunk_id=ids.new(),
                company_id=COMPANY_ID,
                interview_session_id=session_id,
                sequence=1,
                object_key=f"sessions/{session_id}/recording/chunks/000001",
                content_hash=hashlib.sha256(media).hexdigest(),
                byte_size=len(media),
                session_start_ms=1_000,
                session_end_ms=4_000,
                upload_status=UploadStatus.VERIFIED,
                idempotency_key="reporting-runtime-chunk-0001",
                created_at=clock.now(),
            ),
        )
        answer_turn_id = "018f2000-0000-7000-8000-000000000901"
        transcript = await stream.handle_message(
            applicant_context,
            scope,
            _message(
                session_id,
                2,
                "answer.text.submit",
                {
                    "answer_turn_id": answer_turn_id,
                    "text": "복구 지표를 기준으로 장애 격리 정책을 조정했습니다.",
                },
            ),
        )
        assert isinstance(transcript, ProtocolMessage)
        completed = await stream.handle_message(
            applicant_context,
            scope,
            _message(
                session_id,
                2,
                "answer.complete",
                {
                    "answer_turn_id": answer_turn_id,
                    "last_audio_chunk_sequence": 0,
                    "last_recording_chunk_sequence": 1,
                },
            ),
        )
        assert isinstance(completed, tuple)
        assert completed[-1].message_type == "session.completed"

        reporting = SQLAlchemyReportingRouteService(
            database,
            clock=clock,
            id_generator=ids,
        )
        report = reporting.get_report(context=company_context, session_id=session_id)
        timeline = reporting.get_timeline(context=company_context, session_id=session_id)

        assert report["status"] == "ready"
        items = report["items"]
        assert isinstance(items, list) and len(items) == 1
        assert items[0]["assessment_state"] == "confirmed"
        assert items[0]["evidence"][0]["answer_turn_id"] == answer_turn_id
        assert timeline["playback"]["status"] == "partial"
        assert [entry["entry_type"] for entry in timeline["entries"]] == [
            "question",
            "answer",
            "event",
        ]

    engine.dispose()


def _message(
    session_id: str,
    sequence: int,
    message_type: str,
    payload: dict[str, object],
) -> ProtocolMessage:
    return ProtocolMessage(
        protocol_version="1.0",
        message_type=message_type,
        session_id=UUID(session_id),
        sequence=sequence,
        idempotency_key=f"runtime:{message_type}:{sequence}",
        correlation_id=UUID("018f2000-0000-7000-8000-000000000999"),
        sent_at=datetime(2026, 8, 18, tzinfo=UTC),
        payload=payload,
    )
