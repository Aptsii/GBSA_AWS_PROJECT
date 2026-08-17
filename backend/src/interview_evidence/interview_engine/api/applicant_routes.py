"""Applicant equipment, session, resume, and recording intent routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field

from interview_evidence.shared.audit import AuditAppend, AuditAppender, AuditResult
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EquipmentComponent(_ContractModel):
    status: Literal["ready", "warning", "failed"]
    sanitized_code: str | None = Field(default=None, max_length=128)


class EquipmentCheckCreate(_ContractModel):
    camera: EquipmentComponent
    microphone: EquipmentComponent
    network: EquipmentComponent


class InterviewSessionCreate(_ContractModel):
    equipment_check_id: str
    strategy_id: str
    acknowledged_partial_analysis: bool


class RecordingUploadIntentCreate(_ContractModel):
    chunk_sequence: int = Field(ge=1)
    byte_size: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    session_start_ms: int = Field(ge=0)
    session_end_ms: int = Field(ge=1)


class ApplicantInterviewRouteService(Protocol):
    def record_equipment_check(self, **arguments: object) -> dict[str, object]: ...

    def create_interview_session(self, **arguments: object) -> dict[str, object]: ...

    def get_resume_snapshot(self, **arguments: object) -> dict[str, object]: ...

    def create_recording_upload_intent(self, **arguments: object) -> dict[str, object]: ...


@dataclass(slots=True)
class ApplicantInterviewRouteRuntime:
    service: ApplicantInterviewRouteService
    audit_appender: AuditAppender
    scope_provider: Callable[[Request], tuple[TenantContext, ApplicantScope]]


def create_applicant_interview_router(
    runtime: ApplicantInterviewRouteRuntime,
) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/applicant/equipment-checks",
        tags=["Interview"],
        status_code=status.HTTP_201_CREATED,
    )
    async def record_equipment_check(
        payload: EquipmentCheckCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, object]:
        context, scope = runtime.scope_provider(request)
        result = runtime.service.record_equipment_check(
            context=context,
            scope=scope,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )
        await _audit(
            runtime,
            context,
            action="interview.equipment_check",
            resource_type="equipment_check",
            resource_id=_required_id(result, "equipment_check_id"),
            idempotency_key=f"audit-{idempotency_key}",
            metadata={"overall_status": _safe_code(result.get("overall_status"))},
        )
        return result

    @router.post(
        "/applicant/interview-sessions",
        tags=["Interview"],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_interview_session(
        payload: InterviewSessionCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, object]:
        context, scope = runtime.scope_provider(request)
        result = runtime.service.create_interview_session(
            context=context,
            scope=scope,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )
        await _audit(
            runtime,
            context,
            action="interview.session_create",
            resource_type="interview_session",
            resource_id=_required_id(result, "interview_session_id"),
            idempotency_key=f"audit-{idempotency_key}",
            metadata={
                "state": _safe_code(result.get("state")),
                "session_sequence": _safe_int(result.get("session_sequence")),
            },
        )
        return result

    @router.get(
        "/applicant/interview-sessions/{session_id}/resume",
        tags=["Interview"],
    )
    async def get_resume_snapshot(session_id: str, request: Request) -> dict[str, object]:
        context, scope = runtime.scope_provider(request)
        result = runtime.service.get_resume_snapshot(
            context=context,
            scope=scope,
            session_id=session_id,
        )
        await _audit(
            runtime,
            context,
            action="interview.session_resume",
            resource_type="interview_session",
            resource_id=OpaqueId(session_id),
            idempotency_key=f"resume-{context.request_id}",
            metadata={
                "state": _safe_code(result.get("state")),
                "server_sequence": _safe_int(result.get("server_sequence")),
            },
        )
        return result

    @router.post(
        "/applicant/interview-sessions/{session_id}/media-upload-intents",
        tags=["Interview"],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_recording_upload_intent(
        session_id: str,
        payload: RecordingUploadIntentCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, object]:
        context, scope = runtime.scope_provider(request)
        result = runtime.service.create_recording_upload_intent(
            context=context,
            scope=scope,
            session_id=session_id,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )
        await _audit(
            runtime,
            context,
            action="interview.recording_intent",
            resource_type="recording_chunk",
            resource_id=_required_id(result, "recording_chunk_id"),
            idempotency_key=f"audit-{idempotency_key}",
            metadata={"chunk_sequence": payload.chunk_sequence},
        )
        return result

    return router


async def _audit(
    runtime: ApplicantInterviewRouteRuntime,
    context: TenantContext,
    *,
    action: str,
    resource_type: str,
    resource_id: OpaqueId,
    idempotency_key: str,
    metadata: dict[str, str | int | None],
) -> None:
    await runtime.audit_appender.append(
        context,
        AuditAppend(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=AuditResult.SUCCESS,
            metadata=metadata,
            idempotency_key=idempotency_key,
        ),
    )


def _required_id(values: dict[str, object], key: str) -> OpaqueId:
    value = values.get(key)
    if not isinstance(value, str):
        raise ValueError(f"route service result is missing {key}")
    return OpaqueId(value)


def _safe_code(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _safe_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
