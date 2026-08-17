from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from interview_evidence.company_management.adapters.applicant_session import (
    ApplicantSessionAdapter,
)
from interview_evidence.company_management.application.applicant_access_service import (
    ApplicantAccessService,
)
from interview_evidence.company_management.application.hiring_service import HiringService
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.security.principals import ApplicantPrincipal
from interview_evidence.shared.tenant import TenantContext


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApplicantTokenExchange(_ContractModel):
    invitation_token: str = Field(min_length=32, max_length=4_096)


class ApplicantIdentityVerification(_ContractModel):
    display_name: str = Field(min_length=1, max_length=200)
    verification_value: str = Field(min_length=1, max_length=500)


class ConsentCreate(_ContractModel):
    policy_version: str = Field(min_length=1, max_length=128)
    accepted_purposes: list[str] = Field(min_length=1)
    consent_content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")


@dataclass(slots=True)
class ApplicantRouteRuntime:
    access_service: ApplicantAccessService
    hiring_service: HiringService
    session_adapter: ApplicantSessionAdapter | None = None
    cookie_secure: bool = False

    def __post_init__(self) -> None:
        if self.session_adapter is None:
            self.session_adapter = ApplicantSessionAdapter(
                self.hiring_service.repository,
                clock=self.hiring_service.clock,
                id_generator=self.hiring_service.id_generator,
            )


def create_applicant_router(runtime: ApplicantRouteRuntime) -> APIRouter:
    router = APIRouter()

    def scoped(
        request: Request,
        raw_session: str | None,
    ) -> tuple[ApplicantPrincipal, TenantContext]:
        if runtime.session_adapter is None:
            raise RuntimeError("applicant session adapter is not configured")
        principal = runtime.session_adapter.authenticate(raw_session)
        request_id = request.headers.get("x-request-id")
        try:
            checked_request_id = (
                OpaqueId(request_id) if request_id else runtime.access_service.id_generator.new()
            )
        except ValueError:
            checked_request_id = runtime.access_service.id_generator.new()
        return principal, principal.to_tenant_context(
            request_id=str(checked_request_id),
            trace_id=request.headers.get("x-trace-id", "applicant-access-api"),
        )

    @router.post(
        "/applicant/access/exchange",
        tags=["Applicant Access"],
        status_code=status.HTTP_204_NO_CONTENT,
    )
    async def exchange_applicant_invitation_token(
        payload: ApplicantTokenExchange,
        response: Response,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> None:
        del idempotency_key
        if runtime.session_adapter is None:
            raise RuntimeError("applicant session adapter is not configured")
        raw_session, principal = runtime.session_adapter.exchange(payload.invitation_token)
        response.set_cookie(
            "iep_applicant_session",
            raw_session,
            httponly=True,
            secure=runtime.cookie_secure,
            samesite="strict",
            max_age=max(1, int((principal.expires_at - principal.issued_at).total_seconds())),
            path="/v1/applicant",
        )

    @router.post("/applicant/identity-verifications", tags=["Applicant Access"])
    async def verify_applicant_identity(
        payload: ApplicantIdentityVerification,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        raw_session: Annotated[str | None, Cookie(alias="iep_applicant_session")] = None,
    ) -> dict[str, object]:
        principal, context = scoped(request, raw_session)
        return runtime.access_service.verify_identity(
            context,
            principal,
            display_name=payload.display_name,
            verification_value=payload.verification_value,
            idempotency_key=idempotency_key,
        )

    @router.post(
        "/applicant/consents",
        tags=["Applicant Access"],
        status_code=status.HTTP_201_CREATED,
    )
    async def record_applicant_consent(
        payload: ConsentCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
        raw_session: Annotated[str | None, Cookie(alias="iep_applicant_session")] = None,
    ) -> dict[str, object]:
        principal, context = scoped(request, raw_session)
        consent = runtime.access_service.record_consent(
            context,
            principal,
            policy_version=payload.policy_version,
            accepted_purposes=payload.accepted_purposes,
            consent_content_digest=payload.consent_content_digest,
            idempotency_key=idempotency_key,
        )
        return {
            "consent_record_id": str(consent.consent_record_id),
            "policy_version": consent.policy_version,
            "accepted_purposes": sorted(purpose.value for purpose in consent.purposes),
            "retention_days": consent.retention_days,
            "accepted_at": consent.accepted_at.isoformat().replace("+00:00", "Z"),
        }

    return router
