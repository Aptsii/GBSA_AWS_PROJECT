from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

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


def create_reporting_router(runtime: ReportingRouteRuntime) -> APIRouter:
    router = APIRouter()

    @router.get("/interview-sessions/{session_id}/report", tags=["Reporting"])
    def report(session_id: str, request: Request) -> dict[str, object]:
        return runtime.service.get_report(
            context=runtime.context_provider(request), session_id=session_id
        )

    @router.get("/interview-sessions/{session_id}/timeline", tags=["Reporting"])
    def timeline(
        session_id: str,
        request: Request,
        query: Annotated[str | None, Query(max_length=200)] = None,
    ) -> dict[str, object]:
        return runtime.service.get_timeline(
            context=runtime.context_provider(request), session_id=session_id, query=query
        )

    @router.post(
        "/reports/{report_id}/items/{report_item_id}/reviews",
        tags=["Reporting"],
        status_code=status.HTTP_201_CREATED,
    )
    def review(
        report_id: str,
        report_item_id: str,
        payload: HumanAssessmentReviewCreate,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, object]:
        return runtime.service.create_review(
            context=runtime.context_provider(request),
            report_id=report_id,
            report_item_id=report_item_id,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )

    @router.post(
        "/invitations/{invitation_id}/final-decisions",
        tags=["Reporting"],
        status_code=status.HTTP_201_CREATED,
    )
    def decision(
        invitation_id: str,
        payload: FinalDecisionCreate,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, object]:
        return runtime.service.final_decision(
            context=runtime.context_provider(request),
            invitation_id=invitation_id,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )

    @router.post(
        "/privacy/deletion-requests", tags=["Privacy"], status_code=status.HTTP_202_ACCEPTED
    )
    def deletion(
        payload: DeletionRequestCreate,
        request: Request,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, object]:
        return runtime.service.request_deletion(
            context=runtime.context_provider(request),
            idempotency_key=idempotency_key,
            reason=payload.reason,
        )

    @router.get("/privacy/deletion-requests/{deletion_request_id}", tags=["Privacy"])
    def deletion_status(deletion_request_id: str, request: Request) -> dict[str, object]:
        return runtime.service.deletion_status(
            context=runtime.context_provider(request), deletion_request_id=deletion_request_id
        )

    return router
