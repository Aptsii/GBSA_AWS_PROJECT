from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from interview_evidence.shared.tenant import ApplicantScope, TenantContext


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UploadIntentCreate(_ContractModel):
    source_type: Literal["cover_letter", "resume", "pdf"]
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=128)
    byte_size: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class SubmissionCreate(_ContractModel):
    source_type: Literal["cover_letter", "resume", "pdf", "public_git", "public_url"]
    upload_id: str | None = None
    public_url: str | None = None
    candidate_identity_inputs: dict[str, object] | None = None

    @model_validator(mode="after")
    def validate_source(self) -> SubmissionCreate:
        file_source = self.source_type in {"cover_letter", "resume", "pdf"}
        if file_source != (self.upload_id is not None):
            raise ValueError("file sources require upload_id and URL sources require public_url")
        if not file_source and self.public_url is None:
            raise ValueError("URL source requires public_url")
        return self


class SubmissionRouteService(Protocol):
    def create_upload_intent(self, **arguments: object) -> dict[str, object]: ...

    def register_submission(self, **arguments: object) -> dict[str, object]: ...

    def list_submissions(self, **arguments: object) -> list[dict[str, object]]: ...

    def get_readiness(self, **arguments: object) -> dict[str, object]: ...


@dataclass(slots=True)
class ApplicantRouteRuntime:
    service: SubmissionRouteService
    scope_provider: Callable[[Request], tuple[TenantContext, ApplicantScope]]


def create_applicant_router(runtime: ApplicantRouteRuntime) -> APIRouter:
    router = APIRouter()

    @router.post(
        "/applicant/submissions/upload-intents",
        tags=["Submission"],
        status_code=status.HTTP_201_CREATED,
    )
    def create_upload_intent(
        payload: UploadIntentCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, object]:
        context, scope = runtime.scope_provider(request)
        return runtime.service.create_upload_intent(
            context=context,
            scope=scope,
            idempotency_key=idempotency_key,
            **payload.model_dump(),
        )

    @router.post(
        "/applicant/submissions",
        tags=["Submission"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    def register_submission(
        payload: SubmissionCreate,
        request: Request,
        idempotency_key: Annotated[
            str, Header(alias="Idempotency-Key", min_length=16, max_length=128)
        ],
    ) -> dict[str, object]:
        context, scope = runtime.scope_provider(request)
        return runtime.service.register_submission(
            context=context,
            scope=scope,
            idempotency_key=idempotency_key,
            **payload.model_dump(exclude_none=True),
        )

    @router.get("/applicant/submissions", tags=["Submission"])
    def list_submissions(request: Request) -> list[dict[str, object]]:
        context, scope = runtime.scope_provider(request)
        return runtime.service.list_submissions(context=context, scope=scope)

    @router.get("/applicant/analysis-status", tags=["Submission"])
    def get_analysis_status(request: Request) -> dict[str, object]:
        context, scope = runtime.scope_provider(request)
        return runtime.service.get_readiness(context=context, scope=scope)

    return router
