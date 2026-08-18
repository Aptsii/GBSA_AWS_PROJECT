from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from interview_evidence.interview_engine.api.runtime import SQLAlchemyInterviewRouteService
from interview_evidence.interview_engine.domain.turn import UploadStatus
from interview_evidence.interview_engine.repositories.postgres import InterviewSessionRepository
from interview_evidence.shared.aws_clients.ports import FakeObjectStorage, ObjectRef, ProtectedBytes
from interview_evidence.shared.database import Base
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
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
async def test_signed_recording_upload_replays_after_reconnect_and_verifies_contiguously() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    clock = FixedClock(datetime(2026, 8, 18, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x61" * size)
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    storage = FakeObjectStorage()
    content = ProtectedBytes(b"recording-chunk-one")
    digest = hashlib.sha256(content.reveal()).hexdigest()

    with Session(engine) as database:
        repository = InterviewSessionRepository(database)
        first_runtime = SQLAlchemyInterviewRouteService(
            repository,
            clock=clock,
            id_generator=ids,
            object_storage=storage,
        )
        created = first_runtime.create_interview_session(
            context=context,
            scope=scope,
            equipment_check_id="018f2000-0000-7000-8000-000000000201",
            strategy_id=STRATEGY_ID,
            acknowledged_partial_analysis=False,
            idempotency_key="recording-runtime-session-0001",
        )
        session_id = str(created["interview_session_id"])
        arguments = {
            "context": context,
            "scope": scope,
            "session_id": session_id,
            "chunk_sequence": 1,
            "byte_size": len(content.reveal()),
            "sha256": digest,
            "session_start_ms": 0,
            "session_end_ms": 1_000,
            "idempotency_key": "recording-runtime-chunk-0001",
        }

        issued = await first_runtime.create_recording_upload_intent(**arguments)
        reconnected_runtime = SQLAlchemyInterviewRouteService(
            repository,
            clock=clock,
            id_generator=ids,
            object_storage=storage,
        )
        replay = await reconnected_runtime.create_recording_upload_intent(**arguments)

        assert replay["recording_chunk_id"] == issued["recording_chunk_id"]
        recording_chunk_id = OpaqueId(str(issued["recording_chunk_id"]))
        await storage.put(
            context,
            ObjectRef(
                company_id=scope.company_id,
                object_id=recording_chunk_id,
                applicant_scope=scope,
            ),
            content,
            media_type="application/octet-stream",
        )
        assert await reconnected_runtime.verify_recording_chunks(context, scope, session_id, 1) == 1
        stored = repository.list_recording_chunks(context, scope, session_id)
        assert len(stored) == 1
        assert stored[0].upload_status is UploadStatus.VERIFIED
        assert (
            reconnected_runtime.get_resume_snapshot(
                context=context,
                scope=scope,
                session_id=session_id,
            )["last_verified_recording_chunk_sequence"]
            == 1
        )

        with pytest.raises(SafeApplicationError) as conflict:
            await reconnected_runtime.create_recording_upload_intent(
                **{**arguments, "byte_size": len(content.reveal()) + 1}
            )
        assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

    engine.dispose()


@pytest.mark.asyncio
async def test_recording_upload_rejects_overlap_before_issuing_the_next_chunk() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    clock = FixedClock(datetime(2026, 8, 18, tzinfo=UTC))
    ids = UUID7Generator(clock, randbytes=lambda size: b"\x62" * size)
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    content = b"chunk"
    digest = hashlib.sha256(content).hexdigest()

    with Session(engine) as database:
        repository = InterviewSessionRepository(database)
        runtime = SQLAlchemyInterviewRouteService(
            repository,
            clock=clock,
            id_generator=ids,
            object_storage=FakeObjectStorage(),
        )
        created = runtime.create_interview_session(
            context=context,
            scope=scope,
            equipment_check_id="018f2000-0000-7000-8000-000000000201",
            strategy_id=STRATEGY_ID,
            acknowledged_partial_analysis=False,
            idempotency_key="recording-overlap-session-0001",
        )
        session_id = str(created["interview_session_id"])
        await runtime.create_recording_upload_intent(
            context=context,
            scope=scope,
            session_id=session_id,
            chunk_sequence=1,
            byte_size=len(content),
            sha256=digest,
            session_start_ms=0,
            session_end_ms=1_000,
            idempotency_key="recording-overlap-chunk-0001",
        )

        with pytest.raises(SafeApplicationError) as conflict:
            await runtime.create_recording_upload_intent(
                context=context,
                scope=scope,
                session_id=session_id,
                chunk_sequence=2,
                byte_size=len(content),
                sha256=digest,
                session_start_ms=900,
                session_end_ms=1_900,
                idempotency_key="recording-overlap-chunk-0002",
            )
        assert conflict.value.code is ErrorCode.CONFLICT

    engine.dispose()
