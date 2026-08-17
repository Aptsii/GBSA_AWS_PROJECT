from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import timedelta

from fastapi import Request, WebSocket
from sqlalchemy.orm import Session

from interview_evidence.interview_engine.api.applicant_routes import (
    ApplicantInterviewRouteRuntime,
)
from interview_evidence.interview_engine.api.websocket import (
    ProtocolMessage,
    WebSocketRuntime,
)
from interview_evidence.interview_engine.domain.session import InterviewSession, SessionState
from interview_evidence.interview_engine.domain.turn import RecordingChunk, UploadStatus
from interview_evidence.interview_engine.repositories.postgres import InterviewSessionRepository
from interview_evidence.shared.audit import InMemoryAuditAppender
from interview_evidence.shared.aws_clients.ports import ProtectedBytes
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class SQLAlchemyInterviewRouteService:
    __slots__ = ("_clock", "_equipment", "_id_generator", "_replays", "_repository")

    def __init__(
        self,
        repository: InterviewSessionRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._repository = repository
        self._clock = clock
        self._id_generator = id_generator
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
                f"/v1/applicant/interview-sessions/"
                f"{interview_session.interview_session_id}/stream"
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
        context, scope = self._scope(arguments)
        session_id = OpaqueId(str(arguments["session_id"]))
        self._repository.get_session(context, scope, session_id)
        idempotency_key = str(arguments["idempotency_key"])
        sequence = self._required_int(arguments, "chunk_sequence")
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
        return {
            "recording_chunk_id": str(recording_chunk_id),
            "upload_id": str(recording_chunk_id),
            "method": "PUT",
            "url": f"https://uploads.invalid/{recording_chunk_id}",
            "required_headers": {
                "content-type": "application/octet-stream",
                "x-content-sha256": chunk.content_hash,
            },
            "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
        }

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
    __slots__ = ("_clock", "_repository")

    def __init__(self, repository: InterviewSessionRepository, *, clock: Clock) -> None:
        self._repository = repository
        self._clock = clock

    async def handle_message(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        message: ProtocolMessage,
    ) -> ProtocolMessage:
        self._repository.get_session(context, scope, str(message.session_id))
        return message.model_copy(
            update={
                "message_type": "server.ack",
                "sent_at": self._clock.now(),
                "payload": {"accepted_type": message.message_type},
            }
        )

    async def handle_binary(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        metadata: ProtocolMessage,
        content: ProtectedBytes,
    ) -> ProtocolMessage:
        del content
        return await self.handle_message(context, scope, metadata)


def create_interview_runtimes(
    session: Session,
    *,
    http_scope_provider: Callable[[Request], tuple[TenantContext, ApplicantScope]],
    websocket_scope_provider: Callable[[WebSocket], tuple[TenantContext, ApplicantScope]],
    clock: Clock | None = None,
) -> tuple[ApplicantInterviewRouteRuntime, WebSocketRuntime]:
    active_clock = clock or SystemClock()
    id_generator = UUID7Generator(active_clock)
    repository = InterviewSessionRepository(session)
    return (
        ApplicantInterviewRouteRuntime(
            service=SQLAlchemyInterviewRouteService(
                repository,
                clock=active_clock,
                id_generator=id_generator,
            ),
            audit_appender=InMemoryAuditAppender(
                clock=active_clock,
                id_generator=id_generator,
            ),
            scope_provider=http_scope_provider,
        ),
        WebSocketRuntime(
            handler=SQLAlchemyInterviewStreamHandler(repository, clock=active_clock),
            scope_provider=websocket_scope_provider,
        ),
    )
