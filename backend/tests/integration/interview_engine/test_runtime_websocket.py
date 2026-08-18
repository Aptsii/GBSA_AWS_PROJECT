from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from interview_evidence.interview_engine.api.runtime import (
    SQLAlchemyInterviewRouteService,
    SQLAlchemyInterviewStreamHandler,
)
from interview_evidence.interview_engine.api.websocket import ProtocolMessage
from interview_evidence.interview_engine.repositories.postgres import (
    InterviewSessionRepository,
)
from interview_evidence.shared.aws_clients.ports import FakeObjectStorage
from interview_evidence.shared.database import Base
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
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
async def test_sql_websocket_runs_start_complete_and_resume() -> None:
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

        completed = await handler.handle_message(
            context,
            scope,
            _message(
                session_id,
                2,
                "answer.complete",
                {
                    "answer_turn_id": "018f2000-0000-7000-8000-000000000401",
                    "last_recording_chunk_sequence": 0,
                },
            ),
        )
        assert isinstance(completed, tuple)
        assert completed[-1].message_type == "session.completed"
        assert repository.get_session(context, scope, session_id).state.value == "completed"

        resumed = await handler.handle_message(
            context,
            scope,
            _message(session_id, 0, "session.resume", {}),
        )
        assert isinstance(resumed, ProtocolMessage)
        assert resumed.message_type == "resume.snapshot"
        assert resumed.payload["state"] == "completed"
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
        idempotency_key=f"runtime-{message_type}-0001",
        correlation_id=UUID("018f2000-0000-7000-8000-000000000402"),
        sent_at=datetime(2026, 8, 18, tzinfo=UTC),
        payload=payload,
    )
