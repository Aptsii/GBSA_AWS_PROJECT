from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from interview_evidence.company_management.adapters.company_auth import (
    authenticate_company_bearer,
)
from interview_evidence.company_management.application.company_service import CompanyService
from interview_evidence.company_management.application.criteria_service import CriteriaService
from interview_evidence.company_management.application.hiring_service import HiringService
from interview_evidence.shared._validation import FrozenValue
from interview_evidence.shared.audit import (
    AuditAppend,
    AuditAppender,
    AuditResult,
    InMemoryAuditAppender,
)
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.security.principals import (
    CompanyAuthenticator,
    CompanyPrincipal,
)
from interview_evidence.shared.tenant import TenantContext


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PositionCreate(_ContractModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=20_000)


class EvaluationCriterionInput(_ContractModel):
    code: str = Field(pattern=r"^[A-Z0-9_-]{2,40}$")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4_000)
    weight: float = Field(ge=0)
    good_evidence: dict[str, Any]
    weak_evidence: dict[str, Any]
    abstain_guidance: str = Field(min_length=1)
    common_questions: list[str] = Field(default_factory=list)
    required: bool


class CompetencyModelVersionCreate(_ContractModel):
    criteria: list[EvaluationCriterionInput] = Field(min_length=1)
    prohibited_topics: list[str]
    interview_duration_minutes: int = Field(ge=10, le=120)
    persona_definition: dict[str, Any]


class CampaignCreate(_ContractModel):
    position_id: str
    competency_model_version_id: str
    name: str = Field(min_length=1, max_length=200)
    candidate_instructions: str = Field(min_length=1, max_length=10_000)


class InvitationApplicant(_ContractModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)


class InvitationBatchCreate(_ContractModel):
    applicants: list[InvitationApplicant] = Field(min_length=1, max_length=1_000)
    expires_at: datetime


@dataclass(slots=True)
class CompanyRouteRuntime:
    authenticator: CompanyAuthenticator
    company_service: CompanyService
    criteria_service: CriteriaService
    hiring_service: HiringService
    audit_appender: AuditAppender | None = None

    def __post_init__(self) -> None:
        if self.audit_appender is None:
            self.audit_appender = InMemoryAuditAppender(
                clock=self.company_service.clock,
                id_generator=self.company_service.id_generator,
            )


_PROTECTED_AUDIT_KEYS = frozenset(
    {
        "answer",
        "applicant_email",
        "credential",
        "email",
        "raw_token",
        "signed_url",
        "source_text",
        "token",
    }
)


def safe_audit_projection(values: dict[str, object]) -> dict[str, FrozenValue]:
    projection: dict[str, FrozenValue] = {}
    for key, value in values.items():
        normalized_key = key.lower()
        if normalized_key in _PROTECTED_AUDIT_KEYS or "token" in normalized_key:
            continue
        if "url" in normalized_key or "email" in normalized_key or "answer" in normalized_key:
            continue
        if isinstance(value, (str, int, bool)) or value is None:
            projection[key] = value
    return projection


def create_company_router(runtime: CompanyRouteRuntime) -> APIRouter:
    router = APIRouter()

    def scoped(
        request: Request, authorization: str | None
    ) -> tuple[CompanyPrincipal, TenantContext]:
        principal = authenticate_company_bearer(runtime.authenticator, authorization)
        request_id = request.headers.get("x-request-id")
        try:
            checked_request_id = (
                OpaqueId(request_id) if request_id else runtime.company_service.id_generator.new()
            )
        except ValueError:
            checked_request_id = runtime.company_service.id_generator.new()
        trace_id = request.headers.get("x-trace-id", "company-api")
        return principal, principal.to_tenant_context(
            request_id=str(checked_request_id),
            trace_id=trace_id,
        )

    async def audited(
        context: TenantContext,
        *,
        action: str,
        resource_type: str,
        resource_id: str | OpaqueId,
        idempotency_key: str,
        metadata: dict[str, object],
    ) -> None:
        if runtime.audit_appender is None:
            return
        await runtime.audit_appender.append(
            context,
            AuditAppend(
                action=action,
                resource_type=resource_type,
                resource_id=OpaqueId(resource_id),
                result=AuditResult.SUCCESS,
                metadata=safe_audit_projection(metadata),
                idempotency_key=idempotency_key,
            ),
        )

    @router.get("/me", tags=["Company"])
    async def get_current_company_user(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        principal, _ = scoped(request, authorization)
        return runtime.company_service.current_user(principal)

    @router.get("/positions", tags=["Hiring"])
    async def list_positions(
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, object]:
        del cursor
        _, context = scoped(request, authorization)
        positions = runtime.company_service.list_positions(context)[:limit]
        return {"items": [position.to_view() for position in positions], "next_cursor": None}

    @router.post("/positions", tags=["Hiring"], status_code=status.HTTP_201_CREATED)
    async def create_position(
        payload: PositionCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _, context = scoped(request, authorization)
        position = runtime.company_service.create_position(
            context,
            title=payload.title,
            description=payload.description,
        )
        await audited(
            context,
            action="position.create",
            resource_type="position",
            resource_id=position.position_id,
            idempotency_key=idempotency_key,
            metadata={"company_id": str(context.company_id), "result": "created"},
        )
        return position.to_view()

    @router.post(
        "/positions/{position_id}/competency-model-versions",
        tags=["Hiring"],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_competency_model_version(
        position_id: str,
        payload: CompetencyModelVersionCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _, context = scoped(request, authorization)
        version = runtime.criteria_service.create_version(
            context,
            position_id=position_id,
            criteria=[item.model_dump() for item in payload.criteria],
            prohibited_topics=payload.prohibited_topics,
            interview_duration_minutes=payload.interview_duration_minutes,
            persona_definition=payload.persona_definition,
        )
        await audited(
            context,
            action="criterion_version.create",
            resource_type="competency_model_version",
            resource_id=version.competency_model_version_id,
            idempotency_key=idempotency_key,
            metadata={"company_id": str(context.company_id), "result": "created"},
        )
        return version.to_view()

    @router.post(
        "/competency-model-versions/{version_id}/publish",
        tags=["Hiring"],
    )
    async def publish_competency_model_version(
        version_id: str,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        if_match_version: Annotated[int, Header(alias="If-Match-Version", ge=1)],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _, context = scoped(request, authorization)
        version = runtime.criteria_service.publish_version(
            context,
            version_id=version_id,
            expected_version=if_match_version,
        )
        await audited(
            context,
            action="criterion_version.publish",
            resource_type="competency_model_version",
            resource_id=version.competency_model_version_id,
            idempotency_key=idempotency_key,
            metadata={"company_id": str(context.company_id), "result": "published"},
        )
        return version.to_view()

    @router.post("/campaigns", tags=["Hiring"], status_code=status.HTTP_201_CREATED)
    async def create_campaign(
        payload: CampaignCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _, context = scoped(request, authorization)
        campaign = runtime.hiring_service.create_campaign(
            context,
            position_id=payload.position_id,
            competency_model_version_id=payload.competency_model_version_id,
            name=payload.name,
            candidate_instructions=payload.candidate_instructions,
        )
        await audited(
            context,
            action="campaign.create",
            resource_type="campaign",
            resource_id=campaign.campaign_id,
            idempotency_key=idempotency_key,
            metadata={"company_id": str(context.company_id), "result": "created"},
        )
        return campaign.to_view()

    @router.post("/campaigns/{campaign_id}/publish", tags=["Hiring"])
    async def publish_campaign(
        campaign_id: str,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        if_match_version: Annotated[int, Header(alias="If-Match-Version", ge=1)],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _, context = scoped(request, authorization)
        campaign = runtime.hiring_service.publish_campaign(
            context,
            campaign_id=campaign_id,
            expected_version=if_match_version,
        )
        await audited(
            context,
            action="campaign.publish",
            resource_type="campaign",
            resource_id=campaign.campaign_id,
            idempotency_key=idempotency_key,
            metadata={"company_id": str(context.company_id), "result": "published"},
        )
        return campaign.to_view()

    @router.get("/campaigns/{campaign_id}/invitations", tags=["Hiring"])
    async def list_invitations(
        campaign_id: str,
        request: Request,
        authorization: Annotated[str | None, Header()] = None,
        cursor: Annotated[str | None, Query(max_length=512)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> dict[str, object]:
        del cursor
        _, context = scoped(request, authorization)
        invitations = runtime.hiring_service.list_invitations(context, campaign_id)[:limit]
        return {
            "items": [invitation.to_view() for invitation in invitations],
            "next_cursor": None,
        }

    @router.post(
        "/campaigns/{campaign_id}/invitations",
        tags=["Hiring"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def create_invitations(
        campaign_id: str,
        payload: InvitationBatchCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        authorization: Annotated[str | None, Header()] = None,
    ) -> dict[str, object]:
        _, context = scoped(request, authorization)
        invitations = runtime.hiring_service.issue_invitations(
            context,
            campaign_id=campaign_id,
            applicants=[item.model_dump() for item in payload.applicants],
            expires_at=payload.expires_at,
        )
        await audited(
            context,
            action="invitation.issue",
            resource_type="campaign",
            resource_id=campaign_id,
            idempotency_key=idempotency_key,
            metadata={
                "company_id": str(context.company_id),
                "accepted_count": len(invitations),
            },
        )
        return {
            "accepted_count": len(invitations),
            "rejected_count": 0,
            "invitations": [invitation.to_view() for invitation in invitations],
        }

    return router
