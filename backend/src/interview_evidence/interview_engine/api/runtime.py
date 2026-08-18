from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import timedelta
from typing import Protocol
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
    TranscriptionRequest,
    TranscriptionResult,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.messaging.outbox import AggregateRef, OutboxEvent
from interview_evidence.shared.persistence import SQLAlchemyOutbox
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class AudioTranscriber(Protocol):
    async def transcribe(
        self,
        context: TenantContext,
        request: TranscriptionRequest,
    ) -> TranscriptionResult: ...


class StrategySnapshotProvider(Protocol):
    def __call__(
        self,
        context: TenantContext,
        *,
        strategy_id: str,
    ) -> Mapping[str, object]: ...


class InterviewCompletionHandler(Protocol):
    def handle_event(
        self,
        context: TenantContext,
        event: OutboxEvent,
    ) -> Mapping[str, object]: ...


class UnavailableAudioTranscriber:
    async def transcribe(
        self,
        context: TenantContext,
        request: TranscriptionRequest,
    ) -> TranscriptionResult:
        del context, request
        raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE)


class SQLAlchemyInterviewRouteService:
    __slots__ = (
        "_clock",
        "_equipment",
        "_id_generator",
        "_object_storage",
        "_replays",
        "_repository",
        "_strategy_provider",
    )

    def __init__(
        self,
        repository: InterviewSessionRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
        object_storage: ObjectStoragePort,
        strategy_provider: StrategySnapshotProvider | None = None,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._id_generator = id_generator
        self._object_storage = object_storage
        self._strategy_provider = strategy_provider
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
        strategy = self.strategy_snapshot(context, scope, strategy_id)
        status = strategy.get("status")
        if status == "partial" and arguments["acknowledged_partial_analysis"] is not True:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        competency_model_version_id = OpaqueId(str(strategy["competency_model_version_id"]))
        interview_session = InterviewSession(
            interview_session_id=self._id_generator.new(),
            scope=scope,
            interview_strategy_id=strategy_id,
            competency_model_version_id=competency_model_version_id,
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

    def strategy_snapshot(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        strategy_id: str | OpaqueId,
    ) -> Mapping[str, object]:
        ensure_applicant_scope(context, scope)
        checked_id = OpaqueId(strategy_id)
        if self._strategy_provider is None:
            return {
                "company_id": str(scope.company_id),
                "invitation_id": str(scope.invitation_id),
                "interview_strategy_id": str(checked_id),
                "competency_model_version_id": str(checked_id),
                "status": "ready",
                "verification_points": (),
                "common_topics": (),
                "model_config_version": "runtime-fallback-v1",
            }
        snapshot = self._strategy_provider(
            context,
            strategy_id=str(checked_id),
        )
        if (
            snapshot.get("company_id") != str(scope.company_id)
            or snapshot.get("invitation_id") != str(scope.invitation_id)
            or snapshot.get("interview_strategy_id") != str(checked_id)
            or snapshot.get("status") not in {"ready", "partial"}
        ):
            raise SafeApplicationError(ErrorCode.FORBIDDEN)
        return snapshot

    def get_resume_snapshot(self, **arguments: object) -> dict[str, object]:
        context, scope = self._scope(arguments)
        session_id = OpaqueId(str(arguments["session_id"]))
        interview_session = self._repository.get_session(context, scope, session_id)
        checkpoint = self._repository.latest_checkpoint(context, scope, session_id)
        chunks = self._repository.list_recording_chunks(context, scope, session_id)
        verified_sequences = [
            chunk.sequence for chunk in chunks if chunk.upload_status is UploadStatus.VERIFIED
        ]
        pending_turn = None
        if checkpoint is not None and checkpoint.pending_turn_id is not None:
            turn = next(
                (
                    item
                    for item in self._repository.list_turns(context, scope, session_id)
                    if item.turn_id == checkpoint.pending_turn_id
                ),
                None,
            )
            if turn is not None:
                pending_turn = {
                    "turn_id": str(turn.turn_id),
                    "speaker": turn.speaker.value,
                    "status": turn.status.value,
                }
        return {
            "interview_session_id": str(interview_session.interview_session_id),
            "state": interview_session.state.value,
            "server_sequence": interview_session.session_sequence,
            "last_final_turn_id": (
                str(checkpoint.last_final_turn_id)
                if checkpoint is not None and checkpoint.last_final_turn_id is not None
                else None
            ),
            "pending_turn": pending_turn,
            "last_verified_recording_chunk_sequence": max(verified_sequences, default=0),
            "degraded_modes": list(interview_session.degraded_modes),
        }

    async def create_recording_upload_intent(self, **arguments: object) -> dict[str, object]:
        context, scope = self._scope(arguments)
        session_id = OpaqueId(str(arguments["session_id"]))
        self._repository.get_session(context, scope, session_id)
        idempotency_key = str(arguments["idempotency_key"])
        sequence = self._required_int(arguments, "chunk_sequence")
        byte_size = self._required_int(arguments, "byte_size")
        content_hash = str(arguments["sha256"])
        session_start_ms = self._required_int(arguments, "session_start_ms")
        session_end_ms = self._required_int(arguments, "session_end_ms")
        chunks = self._repository.list_recording_chunks(context, scope, session_id)
        replay = next((chunk for chunk in chunks if chunk.idempotency_key == idempotency_key), None)
        if replay is not None:
            if (
                replay.sequence != sequence
                or replay.content_hash != content_hash
                or replay.byte_size != byte_size
                or replay.session_start_ms != session_start_ms
                or replay.session_end_ms != session_end_ms
            ):
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            chunk = replay
        else:
            if sequence != max((chunk.sequence for chunk in chunks), default=0) + 1:
                raise SafeApplicationError(ErrorCode.CONFLICT)
            if chunks and session_start_ms < chunks[-1].session_end_ms:
                raise SafeApplicationError(ErrorCode.CONFLICT)
            recording_chunk_id = self._id_generator.new()
            chunk = RecordingChunk(
                recording_chunk_id=recording_chunk_id,
                company_id=scope.company_id,
                interview_session_id=session_id,
                sequence=sequence,
                object_key=(
                    f"applicant/{scope.company_id}/{scope.applicant_id}/"
                    f"{scope.invitation_id}/{recording_chunk_id}"
                ),
                content_hash=content_hash,
                byte_size=byte_size,
                session_start_ms=session_start_ms,
                session_end_ms=session_end_ms,
                upload_status=UploadStatus.ISSUED,
                idempotency_key=idempotency_key,
                created_at=self._clock.now(),
            )
            self._repository.add_recording_chunk(context, scope, chunk)
        expires_at = self._clock.now() + timedelta(minutes=15)
        signed = await self._object_storage.authorize_upload(
            context,
            ObjectRef(
                company_id=scope.company_id,
                object_id=chunk.recording_chunk_id,
                applicant_scope=scope,
            ),
            media_type="application/octet-stream",
            content_hash=chunk.content_hash,
            byte_size=chunk.byte_size,
            expires_at=expires_at,
        )
        return {
            "recording_chunk_id": str(chunk.recording_chunk_id),
            "upload_id": str(chunk.recording_chunk_id),
            "method": signed.method,
            "url": signed.url,
            "required_headers": dict(signed.required_headers),
            "expires_at": signed.expires_at.isoformat().replace("+00:00", "Z"),
        }

    async def verify_recording_chunks(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        through_sequence: int,
    ) -> int:
        chunks = self._repository.list_recording_chunks(context, scope, session_id)
        last_verified = 0
        for chunk in chunks:
            if chunk.sequence > through_sequence:
                break
            if chunk.sequence != last_verified + 1:
                raise SafeApplicationError(ErrorCode.CONFLICT)
            if chunk.upload_status is not UploadStatus.VERIFIED:
                await self._object_storage.verify_upload(
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
        "_completion_handler",
        "_id_generator",
        "_max_questions",
        "_repository",
        "_route_service",
        "_state_machine",
        "_transcriber",
    )

    def __init__(
        self,
        repository: InterviewSessionRepository,
        route_service: SQLAlchemyInterviewRouteService,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
        transcriber: AudioTranscriber | None = None,
        max_questions: int = 2,
        completion_handler: InterviewCompletionHandler | None = None,
    ) -> None:
        if max_questions < 1:
            raise ValueError("max_questions must be positive")
        self._repository = repository
        self._route_service = route_service
        self._clock = clock
        self._id_generator = id_generator
        self._transcriber = transcriber or UnavailableAudioTranscriber()
        self._max_questions = max_questions
        self._completion_handler = completion_handler
        self._state_machine = SessionStateMachine(clock)

    async def handle_message(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        message: ProtocolMessage,
    ) -> ProtocolMessage | tuple[ProtocolMessage, ...]:
        session = self._repository.get_session(context, scope, str(message.session_id))
        if message.message_type == "session.resume":
            return self._resume(message, context, scope, session)
        if message.message_type != "session.resume" and message.sequence < session.session_sequence:
            return self._resume_message(message, context, scope, session)
        if message.message_type == "session.start":
            return self._start(message, context, scope, session)
        if message.message_type == "question.repeat":
            return self._repeat(message, context, scope, session)
        if message.message_type == "answer.text.submit":
            return self._submit_text(message, context, scope, session)
        if message.message_type == "answer.complete":
            return await self._complete(message, context, scope, session)
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
        session = self._repository.get_session(context, scope, str(metadata.session_id))
        if metadata.sequence < session.session_sequence:
            return self._resume_message(metadata, context, scope, session)
        if metadata.message_type != "audio.chunk.begin":
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if session.state is not SessionState.AWAITING_ANSWER:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        self._validate_audio(metadata, content)
        try:
            transcript = await self._transcriber.transcribe(
                context,
                TranscriptionRequest(
                    company_id=scope.company_id,
                    request_id=OpaqueId(str(metadata.correlation_id)),
                    audio=content,
                    config_version="stt-v1",
                ),
            )
        except SafeApplicationError as error:
            if error.code is not ErrorCode.DEPENDENCY_UNAVAILABLE:
                raise
            return self._pause_message(
                metadata,
                context,
                scope,
                session,
                reason_code="transcription_unavailable",
            )
        answer_turn_id = OpaqueId(str(metadata.payload["answer_turn_id"]))
        turns = self._repository.list_turns(context, scope, session.interview_session_id)
        existing = next((turn for turn in turns if turn.turn_id == answer_turn_id), None)
        if existing is None:
            answer_turn = Turn(
                turn_id=answer_turn_id,
                company_id=scope.company_id,
                interview_session_id=session.interview_session_id,
                sequence=len(turns) + 1,
                speaker=TurnSpeaker.APPLICANT,
                status=TurnStatus.RECORDING,
                text=transcript.text,
                idempotency_key=f"answer-turn:{answer_turn_id}",
                created_at=self._clock.now(),
            )
            self._repository.add_turn(context, scope, answer_turn)
        else:
            if existing.speaker is not TurnSpeaker.APPLICANT or existing.status not in {
                TurnStatus.RECORDING,
                TurnStatus.FINAL,
            }:
                raise SafeApplicationError(ErrorCode.CONFLICT)
            if existing.status is TurnStatus.FINAL:
                return self._transcript_message(metadata, existing, transcript)
            existing_text = existing.text.reveal() if existing.text is not None else ""
            next_text = transcript.text.reveal()
            combined = (
                next_text if existing_text == next_text else f"{existing_text} {next_text}".strip()
            )
            answer_turn = replace(existing, text=ProtectedText(combined))
            self._repository.save_turn(context, scope, answer_turn)
        return self._transcript_message(metadata, answer_turn, transcript)

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
            question = self._next_question(
                context,
                scope,
                awaiting,
                sequence=1,
                question_number=1,
                idempotency_key=message.idempotency_key,
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
                self._question_message(message, context, scope, awaiting, question),
            )
        question = next(turn for turn in reversed(turns) if turn.speaker is TurnSpeaker.INTERVIEWER)
        return (self._question_message(message, context, scope, session, question),)

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
        return self._question_message(message, context, scope, session, question)

    def _submit_text(
        self,
        message: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
    ) -> ProtocolMessage:
        if session.state is not SessionState.AWAITING_ANSWER:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        text_value = message.payload.get("text")
        if not isinstance(text_value, str):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        text = text_value.strip()
        if not 1 <= len(text) <= 20_000:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        try:
            answer_turn_id = OpaqueId(str(message.payload["answer_turn_id"]))
        except (KeyError, ValueError):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None
        turns = self._repository.list_turns(context, scope, session.interview_session_id)
        existing = next((turn for turn in turns if turn.turn_id == answer_turn_id), None)
        if existing is None:
            answer_turn = Turn(
                turn_id=answer_turn_id,
                company_id=scope.company_id,
                interview_session_id=session.interview_session_id,
                sequence=len(turns) + 1,
                speaker=TurnSpeaker.APPLICANT,
                status=TurnStatus.RECORDING,
                text=ProtectedText(text),
                idempotency_key=f"answer-turn:{answer_turn_id}",
                created_at=self._clock.now(),
            )
            self._repository.add_turn(context, scope, answer_turn)
        else:
            if existing.speaker is not TurnSpeaker.APPLICANT:
                raise SafeApplicationError(ErrorCode.CONFLICT)
            if existing.status is TurnStatus.FINAL:
                answer_turn = existing
            elif existing.status is TurnStatus.RECORDING:
                answer_turn = replace(existing, text=ProtectedText(text))
                self._repository.save_turn(context, scope, answer_turn)
            else:
                raise SafeApplicationError(ErrorCode.CONFLICT)
        return self._transcript_message(
            message,
            answer_turn,
            TranscriptionResult(
                text=ProtectedText(text),
                confidence=1.0,
                review_required=False,
            ),
            segment_sequence=0,
            start_ms=0,
            end_ms=0,
        )

    async def _complete(
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
        await self._route_service.verify_recording_chunks(
            context,
            scope,
            session.interview_session_id,
            last_recording_sequence,
        )
        turns = self._repository.list_turns(context, scope, session.interview_session_id)
        answer_turn_id = OpaqueId(str(message.payload["answer_turn_id"]))
        answer_turn = next((turn for turn in turns if turn.turn_id == answer_turn_id), None)
        if (
            answer_turn is None
            or answer_turn.speaker is not TurnSpeaker.APPLICANT
            or answer_turn.status is not TurnStatus.RECORDING
            or answer_turn.text is None
        ):
            return (
                self._pause_message(
                    message,
                    context,
                    scope,
                    session,
                    reason_code="final_transcript_missing",
                ),
            )
        answer_turn = replace(
            answer_turn,
            status=TurnStatus.FINAL,
            finalized_at=self._clock.now(),
        )
        self._repository.save_turn(context, scope, answer_turn)
        final_answers = [
            turn
            for turn in (*turns, answer_turn)
            if turn.speaker is TurnSpeaker.APPLICANT and turn.status is TurnStatus.FINAL
        ]
        if len(final_answers) < self._max_questions:
            preparing = self._state_machine.transition(
                session,
                expected_sequence=session.session_sequence,
                target=SessionState.PREPARING_QUESTION,
            )
            awaiting = self._state_machine.transition(
                preparing,
                expected_sequence=preparing.session_sequence,
                target=SessionState.AWAITING_ANSWER,
            ).with_degraded_mode("text_only")
            self._repository.save_session(
                context,
                awaiting,
                expected_row_version=session.row_version,
            )
            question = self._next_question(
                context,
                scope,
                awaiting,
                sequence=len(turns) + 1,
                question_number=len(final_answers) + 1,
            )
            self._repository.add_turn(context, scope, question)
            checkpoint = self._checkpoint(
                context,
                scope,
                awaiting,
                pending_turn_id=question.turn_id,
                last_final_turn_id=answer_turn.turn_id,
                last_media_sequence=last_recording_sequence,
            )
            return (
                self._message(
                    message,
                    "session.state_changed",
                    awaiting.session_sequence,
                    {
                        "previous_state": session.state.value,
                        "state": awaiting.state.value,
                        "reason_code": "answer_finalized_next_question",
                        "checkpoint_id": str(checkpoint.checkpoint_id),
                    },
                ),
                self._message(
                    message,
                    "question.preparing",
                    awaiting.session_sequence,
                    {"stage": "policy", "degraded_mode": "text_only"},
                ),
                self._question_message(message, context, scope, awaiting, question),
            )
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
            last_final_turn_id=answer_turn.turn_id,
            last_media_sequence=last_recording_sequence,
        )
        self._publish_completion(
            context,
            scope,
            completed,
            last_turn_id=answer_turn.turn_id,
        )
        return (
            self._message(
                message,
                "session.state_changed",
                completed.session_sequence,
                {
                    "previous_state": session.state.value,
                    "state": completed.state.value,
                    "reason_code": "interview_completed",
                    "checkpoint_id": str(checkpoint.checkpoint_id),
                },
            ),
            self._completed_message(message, completed, answer_turn.turn_id),
        )

    def _publish_completion(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
        *,
        last_turn_id: OpaqueId,
    ) -> None:
        if session.completed_at is None:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        chunks = self._repository.list_recording_chunks(
            context, scope, session.interview_session_id
        )
        verified_count = sum(chunk.upload_status is UploadStatus.VERIFIED for chunk in chunks)
        media_status = (
            "ready"
            if chunks and verified_count == len(chunks)
            else "partial"
            if verified_count
            else "pending"
        )
        outbox = SQLAlchemyOutbox(self._repository.session)
        event = outbox.add(
            context,
            OutboxEvent(
                event_id=self._id_generator.new(),
                company_id=scope.company_id,
                event_type="interview.completed",
                event_version=1,
                aggregate=AggregateRef(
                    aggregate_type="interview_session",
                    aggregate_id=session.interview_session_id,
                    version=session.session_sequence,
                ),
                idempotency_key=f"interview-completed:{session.interview_session_id}",
                occurred_at=session.completed_at,
                trace_id=context.trace_id,
                correlation_id=context.request_id,
                causation_id=None,
                payload={
                    "interview_session_id": str(session.interview_session_id),
                    "invitation_id": str(scope.invitation_id),
                    "last_turn_id": str(last_turn_id),
                    "completed_at": session.completed_at.isoformat().replace("+00:00", "Z"),
                    "media_status": media_status,
                },
            ),
        )
        if self._completion_handler is None:
            return
        self._completion_handler.handle_event(context, event)
        outbox.mark_published(context, event.event_id, published_at=self._clock.now())

    def _resume(
        self,
        message: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
    ) -> ProtocolMessage | tuple[ProtocolMessage, ...]:
        snapshot = self._resume_message(message, context, scope, session)
        pending_turn = snapshot.payload.get("pending_turn")
        if snapshot.payload.get("state") != SessionState.AWAITING_ANSWER.value or not isinstance(
            pending_turn, Mapping
        ):
            return snapshot
        pending_turn_id = pending_turn.get("turn_id")
        if not isinstance(pending_turn_id, str):
            return snapshot
        resumed_session = self._repository.get_session(context, scope, session.interview_session_id)
        question = next(
            (
                turn
                for turn in self._repository.list_turns(
                    context, scope, session.interview_session_id
                )
                if str(turn.turn_id) == pending_turn_id and turn.speaker is TurnSpeaker.INTERVIEWER
            ),
            None,
        )
        if question is None:
            return snapshot
        return (
            snapshot,
            self._question_message(message, context, scope, resumed_session, question),
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
        last_verified_sequence = max(
            (chunk.sequence for chunk in chunks if chunk.upload_status is UploadStatus.VERIFIED),
            default=0,
        )
        if session.state is SessionState.PAUSED:
            resumed = self._state_machine.transition(
                session,
                expected_sequence=session.session_sequence,
                target=SessionState.AWAITING_ANSWER,
            )
            self._repository.save_session(
                context,
                resumed,
                expected_row_version=session.row_version,
            )
            checkpoint = self._checkpoint(
                context,
                scope,
                resumed,
                pending_turn_id=(checkpoint.pending_turn_id if checkpoint is not None else None),
                last_final_turn_id=(
                    checkpoint.last_final_turn_id if checkpoint is not None else None
                ),
                last_media_sequence=last_verified_sequence,
            )
            session = resumed
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
                "last_verified_recording_chunk_sequence": last_verified_sequence,
                "allowed_client_messages": self._allowed_client_messages(session.state),
                "degraded_modes": list(session.degraded_modes),
            },
        )

    def _pause_message(
        self,
        request: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
        *,
        reason_code: str,
    ) -> ProtocolMessage:
        paused = self._state_machine.transition(
            session,
            expected_sequence=session.session_sequence,
            target=SessionState.PAUSED,
        ).with_degraded_mode(reason_code)
        self._repository.save_session(
            context,
            paused,
            expected_row_version=session.row_version,
        )
        turns = self._repository.list_turns(context, scope, session.interview_session_id)
        pending_question = next(
            (turn for turn in reversed(turns) if turn.speaker is TurnSpeaker.INTERVIEWER),
            None,
        )
        previous_checkpoint = self._repository.latest_checkpoint(
            context, scope, session.interview_session_id
        )
        chunks = self._repository.list_recording_chunks(
            context, scope, session.interview_session_id
        )
        checkpoint = self._checkpoint(
            context,
            scope,
            paused,
            pending_turn_id=(pending_question.turn_id if pending_question is not None else None),
            last_final_turn_id=(
                previous_checkpoint.last_final_turn_id if previous_checkpoint is not None else None
            ),
            last_media_sequence=max(
                (
                    chunk.sequence
                    for chunk in chunks
                    if chunk.upload_status is UploadStatus.VERIFIED
                ),
                default=0,
            ),
        )
        return self._message(
            request,
            "session.paused",
            paused.session_sequence,
            {
                "reason_code": reason_code,
                "retryable": True,
                "next_retry_at": None,
                "message": "기술적인 문제로 잠시 멈췄습니다. 답변 평가는 영향을 받지 않습니다.",
                "checkpoint_id": str(checkpoint.checkpoint_id),
            },
        )

    def _transcript_message(
        self,
        request: ProtocolMessage,
        answer_turn: Turn,
        transcript: TranscriptionResult,
        *,
        segment_sequence: int | None = None,
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> ProtocolMessage:
        if answer_turn.text is None:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return self._message(
            request,
            "transcript.final",
            request.sequence,
            {
                "answer_turn_id": str(answer_turn.turn_id),
                "transcript_segment_id": str(self._id_generator.new()),
                "segment_sequence": (
                    segment_sequence
                    if segment_sequence is not None
                    else self._payload_int(request, "chunk_sequence")
                ),
                "text": answer_turn.text.reveal(),
                "start_ms": (
                    start_ms
                    if start_ms is not None
                    else self._payload_int(request, "session_start_ms")
                ),
                "end_ms": (
                    end_ms if end_ms is not None else self._payload_int(request, "session_end_ms")
                ),
                "confidence": transcript.confidence,
                "is_final": True,
                "review_required": transcript.review_required,
            },
        )

    def _next_question(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
        *,
        sequence: int,
        question_number: int,
        idempotency_key: str | None = None,
    ) -> Turn:
        question_text, criterion_id, model_config_version, _ = self._strategy_question(
            context,
            scope,
            session,
            question_number=question_number,
        )
        return Turn(
            turn_id=self._id_generator.new(),
            company_id=scope.company_id,
            interview_session_id=session.interview_session_id,
            sequence=sequence,
            speaker=TurnSpeaker.INTERVIEWER,
            status=TurnStatus.PRESENTED,
            text=ProtectedText(question_text),
            target_criterion_id=criterion_id,
            model_config_version=model_config_version,
            idempotency_key=(
                idempotency_key
                or f"server-question:{session.interview_session_id}:{question_number:03d}"
            ),
            created_at=self._clock.now(),
        )

    def _strategy_question(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
        *,
        question_number: int,
    ) -> tuple[str, OpaqueId, str, int]:
        snapshot = self._route_service.strategy_snapshot(
            context,
            scope,
            session.interview_strategy_id,
        )
        model_config_version = str(snapshot.get("model_config_version", "runtime-fallback-v1"))
        points = snapshot.get("verification_points")
        if isinstance(points, (list, tuple)) and points:
            point = points[min(question_number - 1, len(points) - 1)]
            if isinstance(point, Mapping):
                criterion_value = point.get("criterion_id")
                prompt = point.get("prompt")
                source_ids = point.get("source_reference_ids")
                if isinstance(criterion_value, str) and isinstance(prompt, str) and prompt.strip():
                    return (
                        prompt.strip(),
                        OpaqueId(criterion_value),
                        model_config_version,
                        len(source_ids) if isinstance(source_ids, list) else 0,
                    )
        topics = snapshot.get("common_topics")
        if isinstance(topics, (list, tuple)) and topics:
            topic = topics[min(question_number - 1, len(topics) - 1)]
            if isinstance(topic, Mapping):
                criterion_value = topic.get("criterion_id")
                questions = topic.get("common_questions")
                if (
                    isinstance(criterion_value, str)
                    and isinstance(questions, list)
                    and questions
                    and isinstance(questions[0], str)
                ):
                    return (
                        questions[0],
                        OpaqueId(criterion_value),
                        model_config_version,
                        0,
                    )
        fallback_question = (
            "제출한 경험 중 가장 어려웠던 문제와 해결 과정을 구체적으로 설명해 주세요."
            if question_number == 1
            else (
                "앞서 설명한 경험에서 본인이 내린 핵심 판단과 그 결과를 "
                "구체적인 사실로 보완해 주세요."
            )
        )
        return (
            fallback_question,
            session.competency_model_version_id,
            model_config_version,
            0,
        )

    @staticmethod
    def _allowed_client_messages(state: SessionState) -> list[str]:
        if state is SessionState.COMPLETED:
            return []
        if state is SessionState.PAUSED:
            return ["session.resume"]
        if state is SessionState.AWAITING_ANSWER:
            return [
                "client.ack",
                "heartbeat.ping",
                "question.repeat",
                "audio.chunk.begin",
                "answer.text.submit",
                "answer.complete",
            ]
        return ["client.ack", "heartbeat.ping", "session.resume"]

    @classmethod
    def _validate_audio(cls, message: ProtocolMessage, content: ProtectedBytes) -> None:
        raw = content.reveal()
        if cls._payload_int(message, "byte_length") != len(raw):
            raise SafeApplicationError(ErrorCode.CONFLICT)
        if cls._payload_int(message, "chunk_sequence") < 1:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if cls._payload_int(message, "session_end_ms") <= cls._payload_int(
            message, "session_start_ms"
        ):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        digest = message.payload.get("sha256")
        if not isinstance(digest, str) or digest != hashlib.sha256(raw).hexdigest():
            raise SafeApplicationError(ErrorCode.CONFLICT)
        try:
            OpaqueId(str(message.payload["answer_turn_id"]))
        except (KeyError, ValueError):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None

    @staticmethod
    def _payload_int(message: ProtocolMessage, key: str) -> int:
        value = message.payload.get(key)
        if not isinstance(value, int):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        return value

    def _question_message(
        self,
        request: ProtocolMessage,
        context: TenantContext,
        scope: ApplicantScope,
        session: InterviewSession,
        question: Turn,
    ) -> ProtocolMessage:
        if question.text is None or question.target_criterion_id is None:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        _, _, _, source_reference_count = self._strategy_question(
            context,
            scope,
            session,
            question_number=max(1, (question.sequence + 1) // 2),
        )
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
                "source_reference_count": source_reference_count,
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
        last_final_turn_id: OpaqueId | None = None,
    ) -> SessionCheckpoint:
        checkpoint = SessionCheckpoint(
            checkpoint_id=self._id_generator.new(),
            company_id=scope.company_id,
            interview_session_id=session.interview_session_id,
            session_sequence=session.session_sequence,
            last_final_turn_id=last_final_turn_id,
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
    transcriber: AudioTranscriber | None = None,
    strategy_provider: StrategySnapshotProvider | None = None,
    completion_handler: InterviewCompletionHandler | None = None,
    max_questions: int = 2,
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
        strategy_provider=strategy_provider,
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
                transcriber=transcriber,
                max_questions=max_questions,
                completion_handler=completion_handler,
            ),
            scope_provider=websocket_scope_provider,
        ),
    )
