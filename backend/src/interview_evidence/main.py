from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import context as otel_context
from opentelemetry import propagate
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from interview_evidence.company_management.api.applicant_routes import (
    ApplicantRouteRuntime as CompanyApplicantRouteRuntime,
)
from interview_evidence.company_management.api.applicant_routes import (
    create_applicant_router as create_company_applicant_router,
)
from interview_evidence.company_management.api.company_routes import (
    CompanyRouteRuntime,
    create_company_router,
)
from interview_evidence.company_management.events import (
    create_invitation_email_handler,
)
from interview_evidence.interview_engine.api.applicant_routes import (
    ApplicantInterviewRouteRuntime,
    create_applicant_interview_router,
)
from interview_evidence.interview_engine.api.websocket import (
    WebSocketRuntime,
    create_websocket_router,
)
from interview_evidence.reporting.api.company_routes import (
    ReportingRouteRuntime,
    create_reporting_router,
)
from interview_evidence.shared.errors import (
    ErrorCode,
    FieldError,
    SafeApplicationError,
)
from interview_evidence.shared.ids import OpaqueId, UUID7Generator
from interview_evidence.shared.observability import configure_structured_logging
from interview_evidence.submission_analysis.api.applicant_routes import (
    ApplicantRouteRuntime as SubmissionRouteRuntime,
)
from interview_evidence.submission_analysis.api.applicant_routes import (
    create_applicant_router as create_submission_router,
)
from interview_evidence.workers.analysis.handlers import AnalysisJobHandler
from interview_evidence.workers.reporting.media import MediaProcessor
from interview_evidence.workers.reporting.report import ReportGenerator

_REQUEST_IDS = UUID7Generator()


@dataclass(frozen=True, slots=True)
class ApplicationRuntimes:
    company: CompanyRouteRuntime
    company_applicant: CompanyApplicantRouteRuntime
    submission: SubmissionRouteRuntime
    interview: ApplicantInterviewRouteRuntime
    interview_websocket: WebSocketRuntime
    reporting: ReportingRouteRuntime


def create_application_routers(runtimes: ApplicationRuntimes) -> tuple[APIRouter, ...]:
    return (
        create_company_router(runtimes.company),
        create_company_applicant_router(runtimes.company_applicant),
        create_submission_router(runtimes.submission),
        create_applicant_interview_router(runtimes.interview),
        create_websocket_router(runtimes.interview_websocket),
        create_reporting_router(runtimes.reporting),
    )


def create_worker_registry() -> Mapping[str, object]:
    return MappingProxyType(
        {
            "invitation.email_requested": create_invitation_email_handler(),
            "submission.analysis_requested": AnalysisJobHandler(),
            "media.postprocess_requested": MediaProcessor(),
            "report.generation_requested": ReportGenerator(),
        }
    )


def _request_id(request: Request) -> OpaqueId:
    candidate = request.headers.get("x-request-id")
    if candidate is not None:
        try:
            return OpaqueId(candidate)
        except ValueError:
            pass
    return _REQUEST_IDS.new()


def _problem_response(request: Request, error: SafeApplicationError) -> JSONResponse:
    envelope = error.to_envelope(_request_id(request))
    return JSONResponse(
        status_code=envelope.status,
        content=envelope.to_dict(),
        media_type="application/problem+json",
    )


def _safe_validation_fields(error: RequestValidationError) -> tuple[FieldError, ...]:
    fields: list[FieldError] = []
    for issue in error.errors():
        location = ".".join(str(part) for part in issue.get("loc", ()))
        code = str(issue.get("type", "invalid"))
        try:
            fields.append(FieldError(field=location, code=code))
        except ValueError:
            fields.append(FieldError(field="request", code="invalid"))
    return tuple(fields)


class TraceContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        extracted_context = propagate.extract(dict(request.headers))
        token = otel_context.attach(extracted_context)
        try:
            return await call_next(request)
        finally:
            otel_context.detach(token)


def create_app(routers: Iterable[APIRouter] = ()) -> FastAPI:
    configure_structured_logging()
    app = FastAPI(
        title="Interview Evidence Platform API",
        version="1.0.0",
        servers=[{"url": "/v1"}],
    )
    app.add_middleware(TraceContextMiddleware)

    @app.exception_handler(SafeApplicationError)
    async def safe_application_error(
        request: Request,
        error: SafeApplicationError,
    ) -> JSONResponse:
        return _problem_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return _problem_response(
            request,
            SafeApplicationError(
                ErrorCode.INVALID_REQUEST,
                field_errors=_safe_validation_fields(error),
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        del error
        return _problem_response(request, SafeApplicationError(ErrorCode.INTERNAL_ERROR))

    @app.get("/health/live", tags=["health"])
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/ready", tags=["health"])
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    for router in routers:
        app.include_router(router, prefix="/v1")

    FastAPIInstrumentor.instrument_app(app)

    return app


app = create_app()
