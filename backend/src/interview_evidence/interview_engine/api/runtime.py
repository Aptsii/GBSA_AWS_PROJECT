from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

from fastapi import Request, WebSocket
from sqlalchemy.orm import Session

from interview_evidence.interview_engine.api.applicant_routes import (
    ApplicantInterviewRouteRuntime,
)
from interview_evidence.interview_engine.api.websocket import (
    ProtocolMessage,
    WebSocketRuntime,
)
from interview_evidence.interview_engine.application.state_machine import SessionStateMachine
from interview_evidence.interview_engine.domain.session import InterviewSession, SessionState
from interview_evidence.interview_engine.domain.turn import (
    HotViewSyncStatus,
    RecordingChunk,
    SessionCheckpoint,
    Turn,
    TurnSpeaker,
    TurnStatus,
    UploadStatus,
)
from interview_evidence.interview_engine.repositories.postgres import InterviewSessionRepository
from interview_evidence.shared.audit import InMemoryAuditAppender
from interview_evidence.shared.aws_clients.ports import (
    FakeObjectStorage,
    ObjectRef,
    ObjectStoragePort,
    ProtectedBytes,
    ProtectedText,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class SQLAlchemyInterviewRouteService:
    __slots__ = (
        "_clock",
        "_equipment",
        "_id_generator",
        "_object_storage",
        "_replays",
        "_repository",
    )

    def __init__(
        self,
        repository: InterviewSessionRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
        object_storage: ObjectStoragePort,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._id_generator = id_generator
        self._object_storage = object_storage
        self._equipment: dict[tuple[OpaqueId, str], dict[str, object]] = {}
        self._replays: dict[tuple[OpaqueId, str], tuple[str, dict[str, object]]] = {}

    def record_equipment_check(self, **arguments: object) -> dict[str, object]:
        context, scope = self._scope(arguments)
        idempotency_key = str(arguments["idempotency_key"])
        replay_key = (scope.company_id, idempotency_key)
        payload = {
            "camera": arguments["camera"],
            "microphone": arguments["microphone"],
            "network": arguments["network"],
        }
        digest = self._digest(payload)
        replay = self._replay(replay_key, digest)
        if replay is not None:
            return replay
        statuses = [str(component["status"]) for component in payload.values()]  # type: ignore[index]
        overall_status = (
            "failed" if "failed" in statuses else "warning" if "warning" in statuses else "ready"
        )
        response: dict[str, object] = {
            "equipment_check_id": str(self._id_generator.new()),
            **payload,
            "overall_status": overall_status,
            "checked_at": self._clock.now().isoformat().replace("+00:00", "Z"),
        }
        self._equipment[replay_key] = response
        self._record(replay_key, digest, response)
        ensure_applicant_scope(context, scope)
        return response

    def create_interview_session(self, **arguments: object) -> dict[str, object]:
        context, scope = self._scope(arguments)
        idempotency_key = str(arguments["idempotency_key"])
        replay_key = (scope.company_id, idempotency_key)
        digest = self._digest(
            {
                "equipment_check_id": arguments["equipment_check_id"],
                "strategy_id": arguments["strategy_id"],
                "acknowledged_partial_analysis": arguments["acknowledged_partial_analysis"],
            }
        )
        replay = self._replay(replay_key, digest)
        if replay is not None:
            return replay
        strategy_id = OpaqueId(str(arguments["strategy_id"]))
        interview_session = InterviewSession(
            interview_session_id=self._id_generator.new(),
            scope=scope,
            interview_strategy_id=strategy_id,
            competency_model_version_id=strategy_id,
            state=SessionState.PREPARING,
            session_sequence=0,
            row_version=1,
            created_at=self._clock.now(),
        )
        self._repository.add_session(context, interview_session)
        response: dict[str, object] = {
            "interview_session_id": str(interview_session.interview_session_id),
            "state": interview_session.state.value,
            "session_sequence": interview_session.session_sequence,
            "websocket_path": (
                f"/v1/applicant/interview-sessions/{interview_session.interview_session_id}/stream"
            ),
            "protocol_version": "1.0",
        }
        self._record(replay_key, digest, response)
        return response

    def get_resume_snapshot(self, **arguments: object) -> dict[str, object]:
        context, scope = self._scope(arguments)
        session_id = OpaqueId(str(arguments["session_id"]))
        interview_session = self._repository.get_session(context, scope, session_id)
        checkpoint = self._repository.latest_checkpoint(context, scope, session_id)
        chunks = self._repository.list_recording_chunks(context, scope, session_id)
        verified_sequences = [
            chunk.sequence for chunk in chunks if chunk.upload_status is UploadStatus.VERIFIED
        ]
        return {
            "interview_session_id": str(interview_session.interview_session_id),
            "state": interview_session.state.value,
            "server_sequence": interview_session.session_sequence,
            "last_final_turn_id": (
                str(checkpoint.last_final_turn_id)
                if checkpoint is not None and checkpoint.last_final_turn_id is not None
                else None
            ),
            "pending_turn": None,
            "last_verified_recording_chunk_sequence": max(verified_sequences, default=0),
            "degraded_modes": list(interview_session.degraded_modes),
        }

    def create_recording_upload_intent(self, **arguments: object) -> dict[str, object]:
        import asyncio

        context, scope = self._scope(arguments)
        session_id = OpaqueId(str(arguments["session_id"]))
        self._repository.get_session(context, scope, session_id)
        idempotency_key = str(arguments["idempotency_key"])
        sequence = self._required_int(arguments, "chunk_sequence")
        chunks = self._repository.list_recording_chunks(context, scope, session_id)
        if sequence != max((chunk.sequence for chunk in chunks), default=0) + 1:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        recording_chunk_id = self._id_generator.new()
        chunk = RecordingChunk(
            recording_chunk_id=recording_chunk_id,
            company_id=scope.company_id,
            interview_session_id=session_id,
            sequence=sequence,
            object_key=(
                f"recording/{scope.company_id}/{scope.applicant_id}/"
                f"{session_id}/{recording_chunk_id}"
            ),
            content_hash=str(arguments["sha256"]),
            byte_size=self._required_int(arguments, "byte_size"),
            session_start_ms=self._required_int(arguments, "session_start_ms"),
            session_end_ms=self._required_int(arguments, "session_end_ms"),
            upload_status=UploadStatus.ISSUED,
            idempotency_key=idempotency_key,
            created_at=self._clock.now(),
        )
        self._repository.add_recording_chunk(context, scope, chunk)
        expires_at = self._clock.now() + timedelta(minutes=15)
        signed = asyncio.run(
            self._object_storage.authorize_upload(
                context,
                ObjectRef(
                    company_id=scope.company_id,
                    object_id=recording_chunk_id,
                    applicant_scope=scope,
                ),
                media_type="application/octet-stream",
                content_hash=chunk.content_hash,
                byte_size=chunk.byte_size,
                expires_at=expires_at,
            )
        )
        return {
            "recording_chunk_id": str(recording_chunk_id),
            "upload_id": str(recording_chunk_id),
            "method": signed.method,
            "url": signed.url,
            "required_headers": dict(signed.required_headers),
            "expires_at": signed.expires_at.isoformat().replace("+00:00", "Z"),
        }

    def verify_recording_chunks(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        through_sequence: int,
    ) -> int:
        import asyncio

        chunks = self._repository.list_recording_chunks(context, scope, session_id)
        last_verified = 0
        for chunk in chunks:
            if chunk.sequence > through_sequence:
                break
            if chunk.sequence != last_verified + 1:
                raise SafeApplicationError(ErrorCode.CONFLICT)
            if chunk.upload_status is not UploadStatus.VERIFIED:
                asyncio.run(
                    self._object_storage.verify_upload(
                        context,
                        ObjectRef(
                            company_id=scope.company_id,
                            object_id=chunk.recording_chunk_id,
                            applicant_scope=scope,
                        ),
                        media_type="application/octet-stream",
                        content_hash=chunk.content_hash,
                        byte_size=chunk.byte_size,
                    )
                )
                chunk = replace(chunk, upload_status=UploadStatus.VERIFIED)
                self._repository.save_recording_chunk(context, scope, chunk)
            last_verified = chunk.sequence
        if last_verified != through_sequence:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return last_verified

    @staticmethod
    def _scope(arguments: dict[str, object]) -> tuple[TenantContext, ApplicantScope]:
        context = arguments["context"]
        scope = arguments["scope"]
        if not isinstance(context, TenantContext) or not isinstance(scope, ApplicantScope):
            raise TypeError("tenant context and applicant scope are required")
        ensure_applicant_scope(context, scope)
        return context, scope

    def _replay(
        self,
        key: tuple[OpaqueId, str],
        digest: str,
    ) -> dict[str, object] | None:
        existing = self._replays.get(key)
        if existing is None:
            return None
        if existing[0] != digest:
            raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return dict(existing[1])

    def _record(
        self,
        key: tuple[OpaqueId, str],
        digest: str,
        response: dict[str, object],
    ) -> None:
        self._replays[key] = (digest, dict(response))

    @staticmethod
    def _required_int(arguments: dict[str, object], key: str) -> int:
        value = arguments[key]
        if not isinstance(value, int):
            raise TypeError(f"{key} must be an integer")
        return value

    @staticmethod
    def _digest(payload: dict[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()


class SQLAlchemyInterviewStreamHandler:
    __slots__ = (
        "_clock",
        "_id_generator",
        "_repository",
        "_route_service",
        "_state_machine",
    )

    def __init__(
        self,
        repository: InterviewSessionRepository,
        route_service: SQLAlchemyInterviewRouteService,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._repository = repository
        self._route_service = route_service
        self._clock = clock
        self._id_generator = id_generator
        self._state_machine = SessionStateMachine(clock)

    async def handle_message(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        message: ProtocolMessage,
    ) -> ProtocolMessage | tuple[ProtocolMessage, ...]:
        session = self._repository.get_session(context, scope, str(message.session_id))
        if message.message_type != "session.resume" and message.sequence < session.session_sequence:
            return self._resume_message(message, context, scope, session)
        if message.message_type == "session.start":
            return self._start(message, context, scope, session)
        if message.message_type == "question.repeat":
            return self._repeat(message, context, scope, session)
        if message.message_type == "answer.complete":
            return self._complete(message, context, scope, session)
        if message.message_type == "session.resume":
            return self._resume_message(message, context, scope, session)
        return self._message(
            message,
            "server.ack",
            session.session_sequence,
            {"accepted_type": message.message_type},
        )

    async def handle_binary(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        metadata: ProtocolMessage,
        content: ProtectedBytes,
    ) -> ProtocolMessage | tuple[ProtocolMessage, ...]:
        del content
        return await self.handle_message(context, scope, metadata)

    def _start(
        self,
        message: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
    ) -> tuple[ProtocolMessage, ...]:
        turns = self._repository.list_turns(context, scope, session.interview_session_id)
        if not turns:
            previous_state = session.state.value
            in_progress = self._state_machine.transition(
                session,
                expected_sequence=session.session_sequence,
                target=SessionState.IN_PROGRESS,
            )
            awaiting = self._state_machine.transition(
                in_progress,
                expected_sequence=in_progress.session_sequence,
                target=SessionState.AWAITING_ANSWER,
            ).with_degraded_mode("text_only")
            self._repository.save_session(
                context,
                awaiting,
                expected_row_version=session.row_version,
            )
            question = Turn(
                turn_id=self._id_generator.new(),
                company_id=scope.company_id,
                interview_session_id=session.interview_session_id,
                sequence=1,
                speaker=TurnSpeaker.INTERVIEWER,
                status=TurnStatus.PRESENTED,
                text=ProtectedText(
                    "제출한 경험 중 가장 어려웠던 문제와 해결 과정을 구체적으로 설명해 주세요."
                ),
                target_criterion_id=session.competency_model_version_id,
                model_config_version="runtime-fallback-v1",
                idempotency_key=message.idempotency_key,
                created_at=self._clock.now(),
            )
            self._repository.add_turn(context, scope, question)
            checkpoint = self._checkpoint(
                context,
                scope,
                awaiting,
                pending_turn_id=question.turn_id,
                last_media_sequence=0,
            )
            return (
                self._message(
                    message,
                    "session.state_changed",
                    awaiting.session_sequence,
                    {
                        "previous_state": previous_state,
                        "state": awaiting.state.value,
                        "reason_code": "session_started",
                        "checkpoint_id": str(checkpoint.checkpoint_id),
                    },
                ),
                self._question_message(message, awaiting, question),
            )
        question = next(turn for turn in reversed(turns) if turn.speaker is TurnSpeaker.INTERVIEWER)
        return (self._question_message(message, session, question),)

    def _repeat(
        self,
        message: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
    ) -> ProtocolMessage:
        question_id = OpaqueId(str(message.payload["question_turn_id"]))
        question = next(
            turn
            for turn in self._repository.list_turns(context, scope, session.interview_session_id)
            if turn.turn_id == question_id and turn.speaker is TurnSpeaker.INTERVIEWER
        )
        return self._question_message(message, session, question)

    def _complete(
        self,
        message: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
    ) -> tuple[ProtocolMessage, ...]:
        if session.state is SessionState.COMPLETED:
            turns = self._repository.list_turns(context, scope, session.interview_session_id)
            return (self._completed_message(message, session, turns[-1].turn_id),)
        if session.state is not SessionState.AWAITING_ANSWER:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        last_recording_sequence_value = message.payload["last_recording_chunk_sequence"]
        if not isinstance(last_recording_sequence_value, int):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        last_recording_sequence = last_recording_sequence_value
        self._route_service.verify_recording_chunks(
            context,
            scope,
            session.interview_session_id,
            last_recording_sequence,
        )
        turns = self._repository.list_turns(context, scope, session.interview_session_id)
        answer_turn = Turn(
            turn_id=OpaqueId(str(message.payload["answer_turn_id"])),
            company_id=scope.company_id,
            interview_session_id=session.interview_session_id,
            sequence=len(turns) + 1,
            speaker=TurnSpeaker.APPLICANT,
            status=TurnStatus.FAILED,
            idempotency_key=message.idempotency_key,
            created_at=self._clock.now(),
        )
        self._repository.add_turn(context, scope, answer_turn)
        paused = self._state_machine.transition(
            session,
            expected_sequence=session.session_sequence,
            target=SessionState.PAUSED,
        )
        completed = self._state_machine.transition(
            paused,
            expected_sequence=paused.session_sequence,
            target=SessionState.COMPLETED,
        )
        self._repository.save_session(
            context,
            completed,
            expected_row_version=session.row_version,
        )
        checkpoint = self._checkpoint(
            context,
            scope,
            completed,
            pending_turn_id=None,
            last_media_sequence=last_recording_sequence,
        )
        return (
            self._message(
                message,
                "session.state_changed",
                completed.session_sequence,
                {
                    "previous_state": session.state.value,
                    "state": completed.state.value,
                    "reason_code": "answer_received_without_final_transcript",
                    "checkpoint_id": str(checkpoint.checkpoint_id),
                },
            ),
            self._completed_message(message, completed, answer_turn.turn_id),
        )

    def _resume_message(
        self,
        message: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
    ) -> ProtocolMessage:
        checkpoint = self._repository.latest_checkpoint(
            context, scope, session.interview_session_id
        )
        chunks = self._repository.list_recording_chunks(
            context, scope, session.interview_session_id
        )
        pending_turn = None
        if checkpoint is not None and checkpoint.pending_turn_id is not None:
            pending_turn = {
                "turn_id": str(checkpoint.pending_turn_id),
                "speaker": "interviewer",
                "status": "presented",
            }
        return self._message(
            message,
            "resume.snapshot",
            session.session_sequence,
            {
                "state": session.state.value,
                "server_sequence": session.session_sequence,
                "last_final_turn_id": (
                    str(checkpoint.last_final_turn_id)
                    if checkpoint is not None and checkpoint.last_final_turn_id is not None
                    else None
                ),
                "pending_turn": pending_turn,
                "last_verified_recording_chunk_sequence": max(
                    (
                        chunk.sequence
                        for chunk in chunks
                        if chunk.upload_status is UploadStatus.VERIFIED
                    ),
                    default=0,
                ),
                "allowed_client_messages": (
                    ["session.resume"]
                    if session.state is SessionState.PAUSED
                    else ["client.ack", "answer.complete", "audio.chunk.begin"]
                ),
                "degraded_modes": list(session.degraded_modes),
            },
        )

    def _question_message(
        self,
        request: ProtocolMessage,
        session: InterviewSession,
        question: Turn,
    ) -> ProtocolMessage:
        if question.text is None or question.target_criterion_id is None:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return self._message(
            request,
            "question.ready",
            session.session_sequence,
            {
                "question_turn_id": str(question.turn_id),
                "text": question.text.reveal(),
                "target_criterion_id": str(question.target_criterion_id),
                "audio_url": None,
                "audio_expires_at": None,
                "speech_marks_url": None,
                "source_reference_count": 0,
                "text_only": True,
            },
        )

    def _completed_message(
        self,
        request: ProtocolMessage,
        session: InterviewSession,
        last_turn_id: OpaqueId,
    ) -> ProtocolMessage:
        if session.completed_at is None:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return self._message(
            request,
            "session.completed",
            session.session_sequence,
            {
                "completed_at": session.completed_at.isoformat().replace("+00:00", "Z"),
                "last_turn_id": str(last_turn_id),
                "post_processing_status": "partial",
            },
        )

    def _checkpoint(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
        *,
        pending_turn_id: OpaqueId | None,
        last_media_sequence: int,
    ) -> SessionCheckpoint:
        checkpoint = SessionCheckpoint(
            checkpoint_id=self._id_generator.new(),
            company_id=scope.company_id,
            interview_session_id=session.interview_session_id,
            session_sequence=session.session_sequence,
            last_media_chunk_sequence=last_media_sequence,
            pending_turn_id=pending_turn_id,
            hot_view_sync_status=HotViewSyncStatus.PENDING,
            created_at=self._clock.now(),
        )
        return self._repository.add_checkpoint(context, scope, checkpoint)

    def _message(
        self,
        request: ProtocolMessage,
        message_type: str,
        sequence: int,
        payload: dict[str, object],
    ) -> ProtocolMessage:
        return ProtocolMessage(
            protocol_version="1.0",
            message_type=message_type,
            session_id=request.session_id,
            sequence=sequence,
            idempotency_key=f"server:{message_type}:{self._id_generator.new()}",
            correlation_id=UUID(str(self._id_generator.new())),
            sent_at=self._clock.now(),
            payload=payload,
        )


def create_interview_runtimes(
    session: Session,
    *,
    http_scope_provider: Callable[[Request], tuple[TenantContext, ApplicantScope]],
    websocket_scope_provider: Callable[[WebSocket], tuple[TenantContext, ApplicantScope]],
    object_storage: ObjectStoragePort | None = None,
    clock: Clock | None = None,
) -> tuple[ApplicantInterviewRouteRuntime, WebSocketRuntime]:
    active_clock = clock or SystemClock()
    id_generator = UUID7Generator(active_clock)
    repository = InterviewSessionRepository(session)
    active_storage = object_storage or FakeObjectStorage()
    route_service = SQLAlchemyInterviewRouteService(
        repository,
        clock=active_clock,
        id_generator=id_generator,
        object_storage=active_storage,
    )
    return (
        ApplicantInterviewRouteRuntime(
            service=route_service,
            audit_appender=InMemoryAuditAppender(
                clock=active_clock,
                id_generator=id_generator,
            ),
            scope_provider=http_scope_provider,
        ),
        WebSocketRuntime(
            handler=SQLAlchemyInterviewStreamHandler(
                repository,
                route_service,
                clock=active_clock,
                id_generator=id_generator,
            ),
            scope_provider=websocket_scope_provider,
        ),
    )
