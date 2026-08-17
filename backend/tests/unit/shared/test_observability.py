from __future__ import annotations

import io
import json
import logging

from interview_evidence.shared.observability import (
    LogContext,
    RouteTemplate,
    bind_log_context,
    clear_log_context,
    configure_structured_logging,
    inject_trace_context,
    render_safe_json,
    sanitize_event,
)
from opentelemetry import trace
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState


def test_nested_prohibited_fields_are_redacted() -> None:
    sanitized = sanitize_event(
        {
            "event": "request.completed",
            "answer_text": "지원자 답변 원문",
            "nested": {
                "signed_url": "https://example.invalid/secret",
                "safe_code": "DEPENDENCY_TIMEOUT",
            },
        }
    )

    assert sanitized["answer_text"] == "[REDACTED]"
    assert sanitized["nested"]["signed_url"] == "[REDACTED]"
    assert sanitized["nested"]["safe_code"] == "DEPENDENCY_TIMEOUT"


def test_renderer_adds_only_opaque_trace_context() -> None:
    bind_log_context(
        LogContext(
            request_id="018f0f4f-14a6-7b9c-8000-000000000101",
            trace_id="trace-0001",
            company_id="018f0f4f-14a6-7b9c-8000-000000000001",
        )
    )
    try:
        rendered = render_safe_json(None, "info", {"event": "health", "token": "secret"})
    finally:
        clear_log_context()

    payload = json.loads(rendered)
    assert payload["request_id"].endswith("0101")
    assert payload["trace_id"] == "trace-0001"
    assert payload["token"] == "[REDACTED]"
    assert "지원자" not in rendered


def test_transcript_media_url_and_free_form_message_are_redacted() -> None:
    sanitized = sanitize_event(
        {
            "transcript": "원문 자막",
            "audio_url": "https://example.invalid/audio",
            "message": "지원자 답변이 포함될 수 있음",
            "event_id": "018f0f4f-14a6-7b9c-8000-000000000201",
        }
    )

    assert sanitized == {
        "transcript": "[REDACTED]",
        "audio_url": "[REDACTED]",
        "message": "[REDACTED]",
        "event_id": "018f0f4f-14a6-7b9c-8000-000000000201",
    }


def test_clear_context_never_restores_an_older_request() -> None:
    bind_log_context(
        LogContext(
            request_id="018f0f4f-14a6-7b9c-8000-000000000301",
            trace_id="trace-older",
        )
    )
    bind_log_context(
        LogContext(
            request_id="018f0f4f-14a6-7b9c-8000-000000000302",
            trace_id="trace-newer",
        )
    )
    clear_log_context()

    payload = json.loads(render_safe_json(None, "info", {"event": "health"}))

    assert "request_id" not in payload
    assert "trace_id" not in payload


def test_current_open_telemetry_trace_is_injected() -> None:
    span_context = SpanContext(
        trace_id=int("1234567890abcdef1234567890abcdef", 16),
        span_id=int("1234567890abcdef", 16),
        is_remote=False,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )
    span = NonRecordingSpan(span_context)

    with trace.use_span(span, end_on_exit=False):
        carrier = inject_trace_context({})

    assert carrier["traceparent"] == ("00-1234567890abcdef1234567890abcdef-1234567890abcdef-01")


def test_adversarial_aliases_and_exception_objects_never_render() -> None:
    secret_exception = RuntimeError("지원자 원문이 포함된 내부 오류")

    rendered = render_safe_json(
        None,
        "error",
        {
            "event": "worker.failed",
            "text": "지원자 원문",
            "payload": {"content": "문서 원문"},
            "playback_url": "https://signed.invalid/video",
            "applicant_email": "applicant@example.invalid",
            "exception": secret_exception,
            "unexpected_object": secret_exception,
        },
    )

    assert "지원자" not in rendered
    assert "문서 원문" not in rendered
    assert "signed.invalid" not in rendered
    assert "applicant@example.invalid" not in rendered
    assert "RuntimeError" not in rendered
    assert json.loads(rendered)["event"] == "worker.failed"


def test_allowlisted_operational_keys_still_reject_protected_values() -> None:
    sanitized = sanitize_event(
        {
            "event": "지원자 답변 원문",
            "request_id": "지원자 답변 원문",
            "status": "정상처럼 보이는 원문",
            "safe_code": "DEPENDENCY_TIMEOUT",
        }
    )

    assert sanitized["event"] == "[REDACTED]"
    assert sanitized["request_id"] == "[REDACTED]"
    assert sanitized["status"] == "[REDACTED]"
    assert sanitized["safe_code"] == "DEPENDENCY_TIMEOUT"


def test_token_shaped_operational_values_and_concrete_routes_are_redacted() -> None:
    sanitized = sanitize_event(
        {
            "event": "RAWACCESSTOKEN1234567890ABCDEFG",
            "idempotency_key": "RAWACCESSTOKEN1234567890ABCDEFG",
            "route": "/v1/invitations/RAWACCESSTOKEN1234567890ABCDEFG",
        }
    )
    safe = sanitize_event(
        {
            "event": "request.completed",
            "route": RouteTemplate("/v1/invitations/{invitation_id}"),
        }
    )

    assert sanitized["event"] == "[REDACTED]"
    assert sanitized["idempotency_key"] == "[REDACTED]"
    assert sanitized["route"] == "[REDACTED]"
    assert safe["event"] == "request.completed"
    assert safe["route"] == "/v1/invitations/{invitation_id}"


def test_lowercase_answers_and_dotted_secret_values_are_not_operational_codes() -> None:
    for value in ("redis", "secret.token.value"):
        sanitized = sanitize_event(
            {
                "event": value,
                "safe_code": value,
                "trace_id": value,
            }
        )
        assert sanitized == {
            "event": "[REDACTED]",
            "safe_code": "[REDACTED]",
            "trace_id": "[REDACTED]",
        }


def test_stdlib_and_uvicorn_exception_records_drop_messages_and_tracebacks() -> None:
    configure_structured_logging()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("uvicorn.error")
    original_handlers = logger.handlers[:]
    original_propagate = logger.propagate
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    try:
        try:
            raise RuntimeError("protected applicant answer text")
        except RuntimeError:
            logger.exception("server failed with protected applicant answer text")
    finally:
        logger.handlers = original_handlers
        logger.propagate = original_propagate

    output = stream.getvalue()
    assert "protected applicant answer text" not in output
    assert "RuntimeError" not in output
    assert output.strip() == "[REDACTED]"
