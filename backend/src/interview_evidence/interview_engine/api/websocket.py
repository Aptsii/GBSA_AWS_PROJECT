"""Versioned interview WebSocket protocol endpoint."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import UUID7, BaseModel, ConfigDict, Field, field_validator

from interview_evidence.shared.aws_clients.ports import ProtectedBytes
from interview_evidence.shared.tenant import ApplicantScope, TenantContext


class ProtocolMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: Literal["1.0"]
    message_type: str = Field(pattern=r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
    session_id: UUID7
    sequence: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=128)
    correlation_id: UUID7
    sent_at: datetime
    payload: dict[str, object]

    @field_validator("idempotency_key")
    @classmethod
    def validate_idempotency_key(cls, value: str) -> str:
        if any(character.isspace() for character in value):
            raise ValueError("idempotency_key must not contain whitespace")
        return value


class InterviewStreamHandler(Protocol):
    async def handle_message(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        message: ProtocolMessage,
    ) -> ProtocolMessage | tuple[ProtocolMessage, ...]: ...

    async def handle_binary(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        metadata: ProtocolMessage,
        content: ProtectedBytes,
    ) -> ProtocolMessage | tuple[ProtocolMessage, ...]: ...


@dataclass(slots=True)
class WebSocketRuntime:
    handler: InterviewStreamHandler
    scope_provider: Callable[[WebSocket], tuple[TenantContext, ApplicantScope]]


def create_websocket_router(runtime: WebSocketRuntime) -> APIRouter:
    router = APIRouter()

    @router.websocket("/applicant/interview-sessions/{session_id}/stream")
    async def interview_stream(websocket: WebSocket, session_id: str) -> None:
        del session_id
        try:
            context, scope = runtime.scope_provider(websocket)
        except Exception:
            await websocket.close(code=4001)
            return
        await websocket.accept()
        pending_audio: ProtocolMessage | None = None
        try:
            while True:
                received = await websocket.receive()
                if received["type"] == "websocket.disconnect":
                    return
                binary = received.get("bytes")
                if isinstance(binary, bytes):
                    if pending_audio is None:
                        await websocket.close(code=4009)
                        return
                    responses = await runtime.handler.handle_binary(
                        context, scope, pending_audio, ProtectedBytes(binary)
                    )
                    pending_audio = None
                    await _send(websocket, responses)
                    continue
                text = received.get("text")
                if not isinstance(text, str):
                    await websocket.close(code=4009)
                    return
                try:
                    message = ProtocolMessage.model_validate_json(text)
                except ValueError:
                    await websocket.close(code=4009)
                    return
                if message.message_type == "audio.chunk.begin":
                    pending_audio = message
                    continue
                responses = await runtime.handler.handle_message(context, scope, message)
                await _send(websocket, responses)
        except WebSocketDisconnect:
            return
        except Exception:
            await websocket.close(code=1011)

    return router


async def _send(
    websocket: WebSocket,
    responses: ProtocolMessage | tuple[ProtocolMessage, ...],
) -> None:
    items = responses if isinstance(responses, tuple) else (responses,)
    for response in items:
        await websocket.send_json(response.model_dump(mode="json"))
