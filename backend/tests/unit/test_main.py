from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
import structlog
from fastapi import APIRouter
from fastapi.testclient import TestClient
from interview_evidence.main import (
    ApplicationRuntimes,
    create_app,
    create_application_routers,
    create_worker_registry,
)
from interview_evidence.shared.aws_clients.ports import FakeObjectStorage
from interview_evidence.shared.config import RuntimeEnvironment, Settings
from interview_evidence.shared.database import metadata
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock, OpaqueId
from interview_evidence.shared.observability import inject_trace_context
from interview_evidence.shared.security.principals import CompanyPrincipal, FakeCompanyAuthenticator
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)


class ValidationRequest(BaseModel):
    state: str = Field(pattern="^ready$")


def test_health_endpoints_are_available_without_domain_imports() -> None:
    app = create_app(routers=())
    client = TestClient(app)

    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert app.version == "1.0.0"


def test_production_factory_mounts_every_contract_route_and_fails_closed() -> None:
    settings = Settings(
        environment=RuntimeEnvironment.TEST,
        database_url="sqlite+pysqlite:///:memory:",
        applicant_session_secret="test-applicant-session-secret",
        company_jwt_issuer="https://identity.example.test/",
        company_jwt_audience="interview-evidence-api",
        company_jwks_url="https://identity.example.test/.well-known/jwks.json",
        applicant_session_ttl_seconds=3_600,
        invitation_public_base_url="https://applicant.example.test/",
        invitation_email_template="invitation-v1",
        default_retention_days=30,
        signed_url_ttl_seconds=900,
    )
    engine = create_engine(
        settings.database_url.get_secret_value(),
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    authenticator = FakeCompanyAuthenticator(FixedClock(NOW))
    authenticator.register(
        "production-runtime-company-token",
        CompanyPrincipal(
            company_id=OpaqueId("018f2000-0000-7000-8000-000000000100"),
            company_user_id=OpaqueId("018f2000-0000-7000-8000-000000000101"),
            identity_subject="runtime-owner@example.test",
            roles=frozenset({"hiring_admin"}),
            issued_at=NOW,
            expires_at=datetime(2026, 8, 17, 10, 0, tzinfo=UTC),
        ),
    )
    app = create_app(
        settings=settings,
        engine=engine,
        object_storage=FakeObjectStorage(),
        company_authenticator=authenticator,
    )
    paths = app.openapi()["paths"]

    expected_paths = {
        "/v1/me",
        "/v1/positions",
        "/v1/positions/{position_id}/competency-model-versions",
        "/v1/competency-model-versions/{version_id}/publish",
        "/v1/campaigns",
        "/v1/campaigns/{campaign_id}/publish",
        "/v1/campaigns/{campaign_id}/invitations",
        "/v1/applicant/access/exchange",
        "/v1/applicant/identity-verifications",
        "/v1/applicant/consents",
        "/v1/applicant/submissions/upload-intents",
        "/v1/applicant/submissions",
        "/v1/applicant/analysis-status",
        "/v1/applicant/equipment-checks",
        "/v1/applicant/interview-sessions",
        "/v1/applicant/interview-sessions/{session_id}/resume",
        "/v1/applicant/interview-sessions/{session_id}/media-upload-intents",
        "/v1/interview-sessions/{session_id}/report",
        "/v1/interview-sessions/{session_id}/timeline",
        "/v1/reports/{report_id}/items/{report_item_id}/reviews",
        "/v1/interview-sessions/{session_id}/review-artifacts",
        "/v1/invitations/{invitation_id}/final-decisions",
        "/v1/privacy/deletion-requests",
        "/v1/privacy/deletion-requests/{deletion_request_id}",
    }
    assert expected_paths <= set(paths)

    client = TestClient(app)
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/applicant/submissions").status_code == 401
    assert client.get(
        "/v1/interview-sessions/018f2000-0000-7000-8000-000000000310/report"
    ).status_code == 401
    headers = {
        "Authorization": "Bearer production-runtime-company-token",
        "Idempotency-Key": "production-runtime-position-0001",
    }
    created = client.post(
        "/v1/positions",
        headers=headers,
        json={"title": "플랫폼 엔지니어", "description": "런타임 트랜잭션을 검증합니다."},
    )
    assert created.status_code == 201
    listed = client.get(
        "/v1/positions",
        headers={"Authorization": "Bearer production-runtime-company-token"},
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["position_id"] == created.json()["position_id"]
    metadata.drop_all(engine)
    engine.dispose()


def test_public_router_can_be_composed_explicitly() -> None:
    router = APIRouter()

    @router.get("/example")
    def example() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(create_app(routers=(router,)))

    assert client.get("/v1/example").json() == {"ok": True}
    assert client.get("/example").status_code == 404


def test_application_runtime_bundle_wires_every_lane_router(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import interview_evidence.main as main_module

    factory_names = (
        "create_company_router",
        "create_company_applicant_router",
        "create_submission_router",
        "create_applicant_interview_router",
        "create_websocket_router",
        "create_reporting_router",
    )
    for index, factory_name in enumerate(factory_names, start=1):
        router = APIRouter()

        @router.get(f"/fragment-{index}")
        def fragment(index: int = index) -> dict[str, int]:
            return {"fragment": index}

        monkeypatch.setattr(main_module, factory_name, lambda _runtime, router=router: router)

    runtimes = ApplicationRuntimes(
        company=object(),
        company_applicant=object(),
        submission=object(),
        interview=object(),
        interview_websocket=object(),
        reporting=object(),
    )
    client = TestClient(create_app(create_application_routers(runtimes)))

    assert [client.get(f"/v1/fragment-{index}").status_code for index in range(1, 7)] == [
        200,
    ] * 6


def test_worker_registry_contains_every_async_pipeline_handler() -> None:
    registry = create_worker_registry()

    assert set(registry) == {
        "invitation.email_requested",
        "submission.analysis_requested",
        "media.postprocess_requested",
        "report.generation_requested",
    }
    assert all(callable(getattr(handler, "handle_event", None)) for handler in registry.values())


def test_inbound_trace_context_reaches_outbound_carriers() -> None:
    router = APIRouter()

    @router.get("/trace")
    def trace_probe() -> dict[str, str]:
        return dict(inject_trace_context({}))

    traceparent = "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
    response = TestClient(create_app(routers=(router,))).get(
        "/v1/trace", headers={"traceparent": traceparent}
    )

    assert response.json()["traceparent"].split("-")[1] == traceparent.split("-")[1]


def test_safe_application_errors_render_as_problem_json_without_the_cause() -> None:
    router = APIRouter()

    @router.get("/forbidden")
    def forbidden() -> None:
        raise SafeApplicationError(
            ErrorCode.FORBIDDEN,
            cause=RuntimeError("protected applicant answer text"),
        )

    request_id = "018f47a6-1680-7000-8000-0000000000aa"
    response = TestClient(create_app(routers=(router,))).get(
        "/v1/forbidden",
        headers={"x-request-id": request_id},
    )

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "FORBIDDEN"
    assert response.json()["request_id"] == request_id
    assert "protected applicant answer text" not in response.text


def test_app_creation_activates_fail_closed_structured_logging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    structlog.reset_defaults()
    create_app(routers=())

    assert structlog.is_configured()
    structlog.get_logger().info(
        "RAWACCESSTOKEN1234567890ABCDEFG",
        idempotency_key="RAWACCESSTOKEN1234567890ABCDEFG",
        route="/v1/invitations/RAWACCESSTOKEN1234567890ABCDEFG",
    )

    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["event"] == "[REDACTED]"
    assert payload["idempotency_key"] == "[REDACTED]"
    assert payload["route"] == "[REDACTED]"


def test_request_validation_never_echoes_rejected_input() -> None:
    router = APIRouter()

    @router.post("/validate")
    def validate(body: ValidationRequest) -> dict[str, str]:
        return {"state": body.state}

    protected_input = "RAW_APPLICANT_ANSWER_TOKEN_12345"
    response = TestClient(create_app(routers=(router,))).post(
        "/v1/validate",
        json={"state": protected_input},
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INVALID_REQUEST"
    assert response.json()["errors"] == [{"field": "body.state", "code": "string_pattern_mismatch"}]
    assert protected_input not in response.text


def test_unexpected_exceptions_render_a_safe_internal_error() -> None:
    router = APIRouter()

    @router.get("/unexpected")
    def unexpected() -> None:
        raise RuntimeError("protected applicant answer text")

    response = TestClient(
        create_app(routers=(router,)),
        raise_server_exceptions=False,
    ).get("/v1/unexpected")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "protected applicant answer text" not in response.text
