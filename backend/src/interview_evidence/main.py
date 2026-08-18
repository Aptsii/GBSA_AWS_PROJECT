from __future__ import annotations

import os
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from types import MappingProxyType

import boto3  # type: ignore[import-untyped]
from fastapi import APIRouter, FastAPI, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from opentelemetry import context as otel_context
from opentelemetry import propagate
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
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
from interview_evidence.company_management.api.runtime import (
    CompanyAuthorizationFacade,
    CompanyRuntimeBundle,
    create_company_runtime_bundle,
)
from interview_evidence.company_management.events import (
    create_invitation_email_handler,
)
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
)
from interview_evidence.interview_engine.adapters.transcribe import Utf8TextTranscriber
from interview_evidence.interview_engine.api.applicant_routes import (
    ApplicantInterviewRouteRuntime,
    create_applicant_interview_router,
)
from interview_evidence.interview_engine.api.runtime import create_interview_runtimes
from interview_evidence.interview_engine.api.websocket import (
    WebSocketRuntime,
    create_websocket_router,
)
from interview_evidence.reporting.api.company_routes import (
    ReportingRouteRuntime,
    create_reporting_router,
)
from interview_evidence.reporting.api.runtime import create_reporting_runtime
from interview_evidence.shared.aws_clients.ports import ObjectStoragePort
from interview_evidence.shared.aws_clients.s3 import S3ObjectStorage
from interview_evidence.shared.config import RuntimeEnvironment, Settings, TranscriberMode
from interview_evidence.shared.errors import (
    ErrorCode,
    FieldError,
    SafeApplicationError,
)
from interview_evidence.shared.ids import OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.metrics import OperationalMetrics, OperationalMetricsMiddleware
from interview_evidence.shared.observability import configure_structured_logging
from interview_evidence.shared.runtime import (
    DatabaseTransactionMiddleware,
    RequestSessionRegistry,
)
from interview_evidence.shared.security.principals import (
    CompanyAuthenticator,
    CompanyPrincipal,
    FakeCompanyAuthenticator,
)
from interview_evidence.shared.tenant import (
    ApplicantScope,
    TenantContext,
    ensure_company_scope,
)
from interview_evidence.submission_analysis.api.applicant_routes import (
    ApplicantRouteRuntime as SubmissionRouteRuntime,
)
from interview_evidence.submission_analysis.api.applicant_routes import (
    create_applicant_router as create_submission_router,
)
from interview_evidence.submission_analysis.api.runtime import create_submission_runtimes
from interview_evidence.submission_analysis.application.analysis_pipeline import (
    CompanyCriterionSnapshotProvider,
)
from interview_evidence.workers.analysis.runtime import (
    SubmissionAnalysisQueueHandler,
    UnavailableAnalysisQueueHandler,
)
from interview_evidence.workers.reporting.media import MediaProcessor
from interview_evidence.workers.reporting.report import ReportGenerator

_REQUEST_IDS = UUID7Generator()
_SAFE_TRACE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


@dataclass(frozen=True, slots=True)
class RegisteredWorkerHandler:
    implementation: object
    required_payload_fields: tuple[str, ...]
    direct_handle: bool = False

    def handle_event(
        self,
        context: TenantContext,
        event: object,
    ) -> Mapping[str, object]:
        company_id = getattr(event, "company_id", None)
        event_id = getattr(event, "event_id", None)
        payload = getattr(event, "payload", None)
        if company_id is None or event_id is None:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        ensure_company_scope(context, OpaqueId(str(company_id)))
        if not isinstance(payload, Mapping):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        for field in self.required_payload_fields:
            if field not in payload:
                raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        event_handler = getattr(self.implementation, "handle_event", None)
        if callable(event_handler):
            result = event_handler(context, event)
            if not isinstance(result, Mapping):
                raise SafeApplicationError(ErrorCode.INTERNAL_ERROR)
            return result
        if self.direct_handle:
            handler = getattr(self.implementation, "handle", None)
            as_mapping = getattr(event, "as_mapping", None)
            if not callable(handler) or not callable(as_mapping):
                raise SafeApplicationError(ErrorCode.INTERNAL_ERROR)
            result = handler(as_mapping())
            if not isinstance(result, Mapping):
                raise SafeApplicationError(ErrorCode.INTERNAL_ERROR)
            return result
        return {
            "event_id": str(OpaqueId(str(event_id))),
            "status": "queued",
        }


@dataclass(frozen=True, slots=True)
class ApplicationRuntimes:
    company: CompanyRouteRuntime
    company_applicant: CompanyApplicantRouteRuntime
    submission: SubmissionRouteRuntime
    interview: ApplicantInterviewRouteRuntime
    interview_websocket: WebSocketRuntime
    reporting: ReportingRouteRuntime


@dataclass(frozen=True, slots=True)
class ProductionResources:
    settings: Settings
    engine: Engine
    sessions: RequestSessionRegistry
    object_storage: ObjectStoragePort


def create_application_routers(runtimes: ApplicationRuntimes) -> tuple[APIRouter, ...]:
    return (
        create_company_router(runtimes.company),
        create_company_applicant_router(runtimes.company_applicant),
        create_submission_router(runtimes.submission),
        create_applicant_interview_router(runtimes.interview),
        create_websocket_router(runtimes.interview_websocket),
        create_reporting_router(runtimes.reporting),
    )


def create_local_browser_fixture_router(runtime: CompanyRouteRuntime) -> APIRouter:
    router = APIRouter()

    @router.get(
        "/local/browser-fixtures/campaigns/{campaign_id}/invitations/{invitation_id}",
        include_in_schema=False,
    )
    def resolve_invitation_fixture(
        campaign_id: str,
        invitation_id: str,
        request: Request,
    ) -> dict[str, str]:
        principal = runtime.authenticator.authenticate(_authorization_credential(request.headers))
        context = principal.to_tenant_context(
            request_id=str(_request_identifier(request.headers)),
            trace_id=_trace_identifier(request.headers, "local-browser-fixture"),
        )
        invitations = runtime.hiring_service.list_invitations(context, campaign_id)
        if not any(str(item.invitation_id) == invitation_id for item in invitations):
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        return {
            "invitation_id": invitation_id,
            "invitation_token": runtime.hiring_service.get_test_delivery_token(invitation_id),
        }

    return router


def create_worker_registry(
    *,
    session_factory: sessionmaker[Session] | None = None,
    object_storage: ObjectStoragePort | None = None,
) -> Mapping[str, object]:
    if (session_factory is None) != (object_storage is None):
        raise ValueError("analysis worker requires both session factory and object storage")
    analysis_handler: object = UnavailableAnalysisQueueHandler()
    if session_factory is not None and object_storage is not None:
        analysis_clock = SystemClock()

        def criterion_provider_factory(session: Session) -> CompanyCriterionSnapshotProvider:
            return CompanyCriterionSnapshotProvider(
                CompanyAuthorizationFacade(
                    CompanyManagementRepository(session),
                    clock=analysis_clock,
                )
            )

        analysis_handler = SubmissionAnalysisQueueHandler(
            session_factory=session_factory,
            object_storage=object_storage,
            criterion_provider_factory=criterion_provider_factory,
            clock=analysis_clock,
        )
    return MappingProxyType(
        {
            "invitation.email_requested": RegisteredWorkerHandler(
                create_invitation_email_handler(),
                ("invitation_id", "link_resolution_id"),
                direct_handle=True,
            ),
            "submission.analysis_requested": RegisteredWorkerHandler(
                analysis_handler,
                ("submission_id", "analysis_version", "source_type"),
            ),
            "media.postprocess_requested": RegisteredWorkerHandler(
                MediaProcessor(),
                ("session_id", "ordered_chunk_set_id", "output_profile_version"),
            ),
            "report.generation_requested": RegisteredWorkerHandler(
                ReportGenerator(),
                ("session_id", "report_version", "criterion_version_id"),
            ),
        }
    )


def _load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


def _create_object_storage(settings: Settings) -> ObjectStoragePort:
    client = boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
    )
    browser_endpoint = os.getenv("IEP_BROWSER_S3_ENDPOINT_URL")
    presign_client = (
        boto3.client(
            "s3",
            region_name=settings.aws_region,
            endpoint_url=browser_endpoint,
        )
        if browser_endpoint
        else client
    )
    return S3ObjectStorage(
        client,
        bucket=settings.object_storage_bucket,
        presign_client=presign_client,
    )


def _local_company_authenticator(settings: Settings) -> CompanyAuthenticator | None:
    credential = os.getenv("IEP_LOCAL_COMPANY_BEARER")
    if settings.environment is not RuntimeEnvironment.LOCAL or not credential:
        return None
    clock = SystemClock()
    now = clock.now()
    authenticator = FakeCompanyAuthenticator(clock)
    authenticator.register(
        credential,
        CompanyPrincipal(
            company_id=OpaqueId("0198a82a-0540-7000-8000-000000000001"),
            company_user_id=OpaqueId("0198a82a-0540-7000-8000-000000000003"),
            identity_subject="local-owner@example.test",
            roles=frozenset({"hiring_admin", "reviewer"}),
            issued_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(days=365),
        ),
    )
    return authenticator


def _authorization_credential(headers: Mapping[str, str]) -> str:
    authorization = headers.get("authorization")
    if authorization is None:
        raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
    scheme, separator, credential = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not credential:
        raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
    return credential


def _request_identifier(headers: Mapping[str, str]) -> OpaqueId:
    candidate = headers.get("x-request-id")
    if candidate is not None:
        try:
            return OpaqueId(candidate)
        except ValueError:
            pass
    return _REQUEST_IDS.new()


def _trace_identifier(headers: Mapping[str, str], fallback: str) -> str:
    candidate = headers.get("x-trace-id", fallback)
    return candidate if _SAFE_TRACE_ID.fullmatch(candidate) else fallback


def _company_context_provider(
    company: CompanyRuntimeBundle,
) -> Callable[[Request], TenantContext]:
    def provide(request: Request) -> TenantContext:
        principal = company.company.authenticator.authenticate(
            _authorization_credential(request.headers)
        )
        return principal.to_tenant_context(
            request_id=str(_request_identifier(request.headers)),
            trace_id=_trace_identifier(request.headers, "company-api"),
        )

    return provide


def _applicant_scope_provider(
    company: CompanyRuntimeBundle,
) -> Callable[[Request], tuple[TenantContext, ApplicantScope]]:
    def provide(request: Request) -> tuple[TenantContext, ApplicantScope]:
        principal = company.applicant_sessions.authenticate(
            request.cookies.get("iep_applicant_session")
        )
        return (
            principal.to_tenant_context(
                request_id=str(_request_identifier(request.headers)),
                trace_id=_trace_identifier(request.headers, "applicant-api"),
            ),
            principal.applicant_scope(),
        )

    return provide


def _applicant_websocket_scope_provider(
    company: CompanyRuntimeBundle,
) -> Callable[[WebSocket], tuple[TenantContext, ApplicantScope]]:
    def provide(websocket: WebSocket) -> tuple[TenantContext, ApplicantScope]:
        principal = company.applicant_sessions.authenticate(
            websocket.cookies.get("iep_applicant_session")
        )
        return (
            principal.to_tenant_context(
                request_id=str(_request_identifier(websocket.headers)),
                trace_id=_trace_identifier(websocket.headers, "applicant-websocket"),
            ),
            principal.applicant_scope(),
        )

    return provide


def create_production_runtimes(
    resources: ProductionResources,
    *,
    company_authenticator: CompanyAuthenticator | None = None,
) -> ApplicationRuntimes:
    company = create_company_runtime_bundle(
        resources.sessions.proxy,
        resources.settings,
        authenticator=company_authenticator,
    )
    applicant_scope_provider = _applicant_scope_provider(company)
    submission = create_submission_runtimes(
        resources.sessions.proxy,
        authorization_contracts=company.authorization,
        object_storage=resources.object_storage,
        scope_provider=applicant_scope_provider,
    )

    def strategy_provider(
        context: TenantContext,
        *,
        strategy_id: str,
    ) -> Mapping[str, object]:
        return submission.public.get_strategy_snapshot(
            context,
            strategy_id=strategy_id,
        )

    interview, interview_websocket = create_interview_runtimes(
        resources.sessions.proxy,
        http_scope_provider=applicant_scope_provider,
        websocket_scope_provider=_applicant_websocket_scope_provider(company),
        object_storage=resources.object_storage,
        transcriber=(
            Utf8TextTranscriber()
            if resources.settings.transcriber_mode is TranscriberMode.UTF8_TEXT
            else None
        ),
        strategy_provider=strategy_provider,
    )
    return ApplicationRuntimes(
        company=company.company,
        company_applicant=company.applicant,
        submission=submission.applicant,
        interview=interview,
        interview_websocket=interview_websocket,
        reporting=create_reporting_runtime(
            resources.sessions.proxy,
            context_provider=_company_context_provider(company),
        ),
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


def create_app(
    routers: Iterable[APIRouter] | None = None,
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
    object_storage: ObjectStoragePort | None = None,
    company_authenticator: CompanyAuthenticator | None = None,
    metrics: OperationalMetrics | None = None,
) -> FastAPI:
    configure_structured_logging()
    active_metrics = metrics or OperationalMetrics()
    resources: ProductionResources | None = None
    if routers is None:
        active_settings = settings or _load_settings()
        active_engine = engine or create_engine(
            active_settings.database_url.get_secret_value(),
            pool_pre_ping=True,
        )
        resources = ProductionResources(
            settings=active_settings,
            engine=active_engine,
            sessions=RequestSessionRegistry(active_engine),
            object_storage=object_storage or _create_object_storage(active_settings),
        )
        local_company_authenticator = _local_company_authenticator(active_settings)
        runtimes = create_production_runtimes(
            resources,
            company_authenticator=(company_authenticator or local_company_authenticator),
        )
        routers = create_application_routers(runtimes)
        if company_authenticator is None and local_company_authenticator is not None:
            routers = (*routers, create_local_browser_fixture_router(runtimes.company))
    app = FastAPI(
        title="Interview Evidence Platform API",
        version="1.0.0",
        servers=[{"url": "/v1"}],
    )
    app.add_middleware(TraceContextMiddleware)
    if resources is not None:
        app.add_middleware(DatabaseTransactionMiddleware, registry=resources.sessions)
        app.state.production_resources = resources
    app.add_middleware(OperationalMetricsMiddleware, metrics=active_metrics)
    app.state.operational_metrics = active_metrics

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
