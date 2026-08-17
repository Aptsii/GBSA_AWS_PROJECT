from __future__ import annotations

import json

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
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.observability import inject_trace_context
from pydantic import BaseModel, Field


class ValidationRequest(BaseModel):
    state: str = Field(pattern="^ready$")


def test_health_endpoints_are_available_without_domain_imports() -> None:
    app = create_app()
    client = TestClient(app)

    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ready"}
    assert app.version == "1.0.0"


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
    create_app()

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
