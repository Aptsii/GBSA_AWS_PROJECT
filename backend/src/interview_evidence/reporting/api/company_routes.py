from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from interview_evidence.shared.audit import AuditAppend, AuditAppender, AuditResult
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HumanAssessmentReviewCreate(_ContractModel):
    assessment_state: Literal[
        "confirmed", "partially_confirmed", "insufficient_evidence", "needs_follow_up"
    ]
    reason: str = Field(min_length=1, max_length=4000)


class ReviewArtifactCreate(_ContractModel):
    review_type: Literal["note", "bookmark"]
    target_id: str
    value: dict[str, object]
    reason: str | None = None


class FinalDecisionCreate(_ContractModel):
    decision: Literal["advance", "reject", "hold", "withdrawn"]
    reason: str = Field(min_length=1, max_length=4000)


class DeletionRequestCreate(_ContractModel):
    reason: str = Field(min_length=1, max_length=1000)


class ReportingRouteService(Protocol):
    def get_report(self, **arguments: object) -> dict[str, object]: ...
    def get_timeline(self, **arguments: object) -> dict[str, object]: ...
    def create_review(self, **arguments: object) -> dict[str, object]: ...
    def create_artifact(self, **arguments: object) -> dict[str, object]: ...
    def final_decision(self, **arguments: object) -> dict[str, object]: ...
    def request_deletion(self, **arguments: object) -> dict[str, object]: ...
    def deletion_status(self, **arguments: object) -> dict[str, object]: ...


@dataclass(slots=True)
class ReportingRouteRuntime:
    service: ReportingRouteService
    context_provider: Callable[[Request], TenantContext]
    audit_appender: AuditAppender | None = None


def create_reporting_router(runtime: ReportingRouteRuntime) -> APIRouter:
    router = APIRouter()

    async def audited(
        context: TenantContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str | OpaqueId,
        seed: str,
        metadata: dict[str, str | bool | int | None],
    ) -> None:
        if runtime.audit_appender is None:
            return
        checked_resource_id = OpaqueId(resource_id)
        digest = hashlib.sha256(f"{seed}|{action}|{checked_resource_id}".encode()).hexdigest()
        await runtime.audit_appender.append(
            context,
            AuditAppend(
                action=action,
                resource_type=resource_type,
                resource_id=checked_resource_id,
                result=AuditResult.SUCCESS,
                metadata=metadata,
                idempotency_key=f"audit-{digest}",
            ),
        )

    @router.get("/interview-sessions/{session_id}/report", tags=["Reporting"])
    async def report(session_id: str, request: Request) -> dict[str, object]:
        context = runtime.context_provider(request)
        result = runtime.service.get_report(context=context, session_id=session_id)
        await audited(
            context,
            action="reporting.report_viewed",
            resource_type="interview_session",
            resource_id=session_id,
            seed=str(context.request_id),
            metadata={},
        )
        return result

    @router.get("/interview-sessions/{session_id}/timeline", tags=["Reporting"])
    async def timeline(
        session_id: str,
        request: Request,
        query: Annotated[str | None, Query(max_length=200)] = None,
    ) -> dict[str, object]:
        context = runtime.context_provider(request)
        result = runtime.service.get_timeline(context=context, session_id=session_id, query=query)
        await audited(
            context,
            action="reporting.timeline_viewed",
            resource_type="interview_session",
            resource_id=session_id,
            seed=str(context.request_id),
            metadata={"query_applied": query is not None},
        )
        return result

    @router.post(
        "/reports/{report_id}/items/{report_item_id}/reviews",
        tags=["Reporting"],
        status_code=status.HTTP_201_CREATED,
    )
    async def review(
        report_id: str,
        report_item_id: str,
        payload: HumanAssessmentReviewCreate,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, object]:
        context = runtime.context_provider(request)
        result = runtime.service.create_review(
            context=context,
            report_id=report_id,
            report_item_id=report_item_id,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )
        await audited(
            context,
            action="reporting.assessment_review_created",
            resource_type="report_item",
            resource_id=report_item_id,
            seed=idempotency_key,
            metadata={"assessment_state": payload.assessment_state},
        )
        return result

    @router.post(
        "/interview-sessions/{session_id}/review-artifacts",
        tags=["Reporting"],
        status_code=status.HTTP_201_CREATED,
    )
    async def artifact(
        session_id: str,
        payload: ReviewArtifactCreate,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, object]:
        context = runtime.context_provider(request)
        result = runtime.service.create_artifact(
            context=context,
            session_id=session_id,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )
        await audited(
            context,
            action="reporting.review_artifact_created",
            resource_type="interview_session",
            resource_id=session_id,
            seed=idempotency_key,
            metadata={"review_type": payload.review_type},
        )
        return result

    @router.post(
        "/invitations/{invitation_id}/final-decisions",
        tags=["Reporting"],
        status_code=status.HTTP_201_CREATED,
    )
    async def decision(
        invitation_id: str,
        payload: FinalDecisionCreate,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, object]:
        context = runtime.context_provider(request)
        result = runtime.service.final_decision(
            context=context,
            invitation_id=invitation_id,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )
        await audited(
            context,
            action="reporting.final_decision_recorded",
            resource_type="invitation",
            resource_id=invitation_id,
            seed=idempotency_key,
            metadata={"decision": payload.decision},
        )
        return result

    @router.post(
        "/privacy/deletion-requests", tags=["Privacy"], status_code=status.HTTP_202_ACCEPTED
    )
    async def deletion(
        payload: DeletionRequestCreate,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, object]:
        context = runtime.context_provider(request)
        result = runtime.service.request_deletion(
            context=context,
            idempotency_key=idempotency_key,
            reason=payload.reason,
        )
        deletion_request_id = _required_result_id(result, "deletion_request_id")
        await audited(
            context,
            action="reporting.deletion_requested",
            resource_type="deletion_request",
            resource_id=deletion_request_id,
            seed=idempotency_key,
            metadata={},
        )
        return result

    @router.get("/privacy/deletion-requests/{deletion_request_id}", tags=["Privacy"])
    async def deletion_status(deletion_request_id: str, request: Request) -> dict[str, object]:
        context = runtime.context_provider(request)
        result = runtime.service.deletion_status(
            context=context, deletion_request_id=deletion_request_id
        )
        await audited(
            context,
            action="reporting.deletion_status_viewed",
            resource_type="deletion_request",
            resource_id=deletion_request_id,
            seed=str(context.request_id),
            metadata={},
        )
        return result

    return router


def _required_result_id(result: dict[str, object], key: str) -> OpaqueId:
    value = result.get(key)
    if not isinstance(value, str):
        raise ValueError(f"route service result is missing {key}")
    return OpaqueId(value)
