from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import structlog
from fastapi import APIRouter
from fastapi.testclient import TestClient
from interview_evidence.main import (
    ApplicationRuntimes,
    RegisteredWorkerHandler,
    create_app,
    create_application_routers,
    create_worker_registry,
)
from interview_evidence.shared.aws_clients.ports import FakeObjectStorage
from interview_evidence.shared.config import RuntimeEnvironment, Settings
from interview_evidence.shared.database import metadata
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock, OpaqueId
from interview_evidence.shared.metrics import (
    InMemoryMetricSink,
    MetricName,
    OperationalMetrics,
)
from interview_evidence.shared.observability import inject_trace_context
from interview_evidence.shared.security.principals import CompanyPrincipal, FakeCompanyAuthenticator
from interview_evidence.shared.tenant import ActorType, TenantContext
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
    assert not any(path.startswith("/v1/local/") for path in paths)

    client = TestClient(app)
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/applicant/submissions").status_code == 401
    assert (
        client.get("/v1/interview-sessions/018f2000-0000-7000-8000-000000000310/report").status_code
        == 401
    )
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


def test_local_browser_fixture_releases_invitation_token_only_to_local_company(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credential = "local-browser-fixture-token"
    monkeypatch.setenv("IEP_LOCAL_COMPANY_BEARER", credential)
    settings = Settings(
        environment=RuntimeEnvironment.LOCAL,
        database_url="sqlite+pysqlite:///:memory:",
        applicant_session_secret="local-browser-applicant-session-secret",
        company_jwt_issuer="https://identity.local.invalid/",
        company_jwt_audience="interview-evidence-api",
        company_jwks_url="https://identity.local.invalid/.well-known/jwks.json",
        applicant_session_ttl_seconds=3_600,
        invitation_public_base_url="http://localhost:5174/",
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
    client = TestClient(
        create_app(
            settings=settings,
            engine=engine,
            object_storage=FakeObjectStorage(),
        )
    )
    headers = {
        "Authorization": f"Bearer {credential}",
        "Idempotency-Key": "local-browser-position-0001",
    }
    position = client.post(
        "/v1/positions",
        headers=headers,
        json={"title": "브라우저 검증 직무", "description": "로컬 E2E 전용 직무입니다."},
    ).json()
    position_id = position["position_id"]
    criterion = client.post(
        f"/v1/positions/{position_id}/competency-model-versions",
        headers={**headers, "Idempotency-Key": "local-browser-criterion-0001"},
        json={
            "criteria": [
                {
                    "code": "DELIVERY",
                    "name": "실행력",
                    "description": "실제 경험과 결과를 설명합니다.",
                    "weight": 1,
                    "good_evidence": {"guidance": "역할과 결과가 구체적임"},
                    "weak_evidence": {"guidance": "설명이 추상적임"},
                    "abstain_guidance": "근거가 부족하면 판단을 유보합니다.",
                    "common_questions": ["최근 결과를 만든 경험을 설명해 주세요."],
                    "required": True,
                }
            ],
            "prohibited_topics": [],
            "interview_duration_minutes": 30,
            "persona_definition": {"name": "하루", "tone": "professional"},
        },
    ).json()
    criterion_id = criterion["competency_model_version_id"]
    published = client.post(
        f"/v1/competency-model-versions/{criterion_id}/publish",
        headers={
            **headers,
            "Idempotency-Key": "local-browser-criterion-publish-0001",
            "If-Match-Version": "1",
        },
    )
    assert published.status_code == 200
    campaign = client.post(
        "/v1/campaigns",
        headers={**headers, "Idempotency-Key": "local-browser-campaign-0001"},
        json={
            "position_id": position_id,
            "competency_model_version_id": criterion_id,
            "name": "로컬 브라우저 캠페인",
            "candidate_instructions": "동의 후 면접을 진행합니다.",
        },
    ).json()
    campaign_id = campaign["campaign_id"]
    published_campaign = client.post(
        f"/v1/campaigns/{campaign_id}/publish",
        headers={
            **headers,
            "Idempotency-Key": "local-browser-campaign-publish-0001",
            "If-Match-Version": "1",
        },
    )
    assert published_campaign.status_code == 200
    invitation_response = client.post(
        f"/v1/campaigns/{campaign_id}/invitations",
        headers={**headers, "Idempotency-Key": "local-browser-invitation-0001"},
        json={
            "applicants": [
                {
                    "email": "local-browser-applicant@example.test",
                    "display_name": "브라우저 지원자",
                }
            ],
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert invitation_response.status_code == 202
    invitation_id = invitation_response.json()["invitations"][0]["invitation_id"]
    fixture_path = f"/v1/local/browser-fixtures/campaigns/{campaign_id}/invitations/{invitation_id}"

    assert client.get(fixture_path).status_code == 401
    fixture = client.get(fixture_path, headers={"Authorization": f"Bearer {credential}"})
    assert fixture.status_code == 200
    assert fixture.json()["invitation_id"] == invitation_id
    assert fixture.json()["invitation_token"]
    assert (
        client.post(
            "/v1/applicant/access/exchange",
            headers={"Idempotency-Key": "local-browser-exchange-0001"},
            json={"invitation_token": fixture.json()["invitation_token"]},
        ).status_code
        == 204
    )

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


def test_registered_worker_handler_executes_event_aware_implementation() -> None:
    class EventAwareImplementation:
        def handle_event(self, _context: TenantContext, event: object) -> dict[str, object]:
            return {"event_id": str(event.event_id), "status": "ready"}

    context = TenantContext(
        company_id=OpaqueId("018f2000-0000-7000-8000-000000000100"),
        actor_type=ActorType.SYSTEM,
        actor_id=OpaqueId("018f2000-0000-7000-8000-000000000101"),
        request_id=OpaqueId("018f2000-0000-7000-8000-000000000102"),
        trace_id="worker-test",
    )
    event = SimpleNamespace(
        company_id=context.company_id,
        event_id=OpaqueId("018f2000-0000-7000-8000-000000000901"),
        payload={"submission_id": "submission"},
    )
    handler = RegisteredWorkerHandler(
        EventAwareImplementation(),
        ("submission_id",),
    )

    assert handler.handle_event(context, event)["status"] == "ready"


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


def test_api_boundary_records_versioned_latency_retry_reconciliation_and_degraded_metrics() -> None:
    router = APIRouter()

    @router.get("/interview-sessions/{session_id}/resume")
    def resume(session_id: str) -> dict[str, object]:
        del session_id
        return {
            "degraded_modes": ["search_fallback"],
            "retry_count": 2,
            "reconciliation_lag_ms": 750,
        }

    sink = InMemoryMetricSink()
    metrics = OperationalMetrics(sink)
    response = TestClient(create_app(routers=(router,), metrics=metrics)).get(
        "/v1/interview-sessions/018f2000-0000-7000-8000-000000000300/resume"
    )

    assert response.status_code == 200
    assert {metric.name for metric in sink.metrics} == {
        MetricName.STAGE_LATENCY,
        MetricName.RETRY,
        MetricName.RECONCILIATION_LAG,
        MetricName.DEGRADED_MODE,
    }
    assert all(metric.operation_version == "api-v1" for metric in sink.metrics)
    assert all(metric.stage == "interview" for metric in sink.metrics)


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
