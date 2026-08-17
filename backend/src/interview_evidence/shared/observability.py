from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, MutableMapping, Sequence
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from typing import Any

import structlog
from interview_evidence.shared.ids import OpaqueId
from opentelemetry import propagate, trace

REDACTED = "[REDACTED]"
_BASE_LOG_RECORD_FACTORY = logging.getLogRecordFactory()
PROHIBITED_FIELDS = frozenset(
    {
        "answer",
        "answer_text",
        "applicant_answer",
        "applicant_source",
        "authorization",
        "credential",
        "credentials",
        "content",
        "document",
        "document_text",
        "email",
        "exception",
        "headers",
        "idempotency_key",
        "message",
        "name",
        "password",
        "payload",
        "raw_text",
        "secret",
        "signed_url",
        "source_text",
        "text",
        "token",
        "traceback",
        "transcript",
        "transcript_text",
        "audio_url",
        "video_url",
    }
)
SAFE_STRING_FIELDS = frozenset(
    {
        "event",
        "level",
        "method",
        "request_id",
        "result",
        "route",
        "span_id",
        "state",
        "trace_id",
    }
)
SAFE_OPERATIONAL_VALUE = re.compile(r"^[A-Za-z0-9_.:@+-]{1,256}$")
SPAN_ID = re.compile(r"^[a-f0-9]{16}$")
TRACE_ID = re.compile(r"^(?:[a-f0-9]{32}|trace-[0-9]{1,16})$")
VERSION_VALUE = re.compile(r"^(?:[0-9]+\.[0-9]+|[a-z][a-z0-9-]{0,63}-v[0-9]+)$")
ROUTE_TEMPLATE = re.compile(
    r"^/(?:[a-z0-9][a-z0-9_-]{0,63}|\{[a-z][a-z0-9_]{0,63}\})"
    r"(?:/(?:[a-z0-9][a-z0-9_-]{0,63}|\{[a-z][a-z0-9_]{0,63}\}))*$"
)
SAFE_LOG_EVENTS = frozenset(
    {
        "health",
        "request.completed",
        "worker.failed",
        "deletion.requested",
        "deletion.target_requested",
        "deletion.target_verified",
        "interview.completed",
        "interview.session_paused",
        "interview.turn_finalized",
        "invitation.consent_completed",
        "media.postprocess_requested",
        "report.generation_requested",
        "report.ready",
        "retention.expired",
        "strategy.ready",
        "submission.analysis_completed",
        "submission.analysis_requested",
        "answer.complete",
        "audio.chunk.begin",
        "client.ack",
        "error",
        "heartbeat.ping",
        "question.preparing",
        "question.ready",
        "question.repeat",
        "resume.snapshot",
        "session.completed",
        "session.paused",
        "session.resume",
        "session.start",
        "session.state_changed",
        "transcript.final",
        "transcript.partial",
    }
)
SAFE_ENUM_VALUES = frozenset(
    {
        "accepted",
        "applicant",
        "applicant_answer",
        "awaiting_answer",
        "completed",
        "confirmed",
        "consented",
        "denied",
        "failed",
        "final",
        "insufficient_evidence",
        "materials_submitted",
        "partial",
        "partially_confirmed",
        "paused",
        "pending",
        "pdf",
        "presented",
        "preparing",
        "preparing_question",
        "published",
        "queued",
        "ready",
        "report",
        "retrying",
        "review_required",
        "session",
        "submission",
        "submission_chunk",
        "succeeded",
        "verified",
        "verified_absent",
    }
)
SAFE_ERROR_CODES = frozenset(
    {
        "AUTHENTICATION_EXPIRED",
        "AUTHENTICATION_REQUIRED",
        "CONFLICT",
        "DEPENDENCY_TIMEOUT",
        "DEPENDENCY_UNAVAILABLE",
        "FORBIDDEN",
        "IDEMPOTENCY_CONFLICT",
        "INTERNAL_ERROR",
        "INVALID_REQUEST",
        "NETWORK_INTERRUPTION",
        "ONE_SOURCE_UNAVAILABLE",
        "RATE_LIMITED",
        "RESOURCE_NOT_FOUND",
        "STALE_VERSION",
        "TEMPORARY_STORE_UNAVAILABLE",
        "TENANT_CONTEXT_REQUIRED",
        "TENANT_SCOPE_DENIED",
        "answer_finalized",
    }
)


class RouteTemplate(str):
    """Explicitly trusted framework route template, never a concrete request path."""

    def __new__(cls, value: str) -> RouteTemplate:
        if ROUTE_TEMPLATE.fullmatch(value) is None:
            raise ValueError("route must be a parameterized framework template")
        return str.__new__(cls, value)


@dataclass(frozen=True, slots=True)
class LogContext:
    request_id: str | None = None
    trace_id: str | None = None
    company_id: str | None = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("request_id", "company_id", "session_id"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, str(OpaqueId(value)))
        if self.trace_id is not None and SAFE_OPERATIONAL_VALUE.fullmatch(self.trace_id) is None:
            raise ValueError("trace_id must be an opaque safe code")


_LOG_CONTEXT: ContextVar[LogContext | None] = ContextVar("log_context", default=None)


def bind_log_context(context: LogContext) -> None:
    _LOG_CONTEXT.set(context)


def clear_log_context() -> None:
    _LOG_CONTEXT.set(None)


def _is_prohibited(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return normalized in PROHIBITED_FIELDS or any(
        marker in normalized
        for marker in (
            "answer",
            "content",
            "credential",
            "email",
            "exception",
            "headers",
            "document_text",
            "message",
            "name",
            "password",
            "payload",
            "secret",
            "signed_url",
            "source_text",
            "text",
            "token",
            "traceback",
            "transcript",
            "url",
        )
    )


def _is_safe_string_field(key: str | None) -> bool:
    if key is None:
        return False
    normalized = key.casefold().replace("-", "_")
    return normalized in SAFE_STRING_FIELDS or normalized.endswith(
        ("_at", "_code", "_id", "_status", "_type", "_version")
    )


def _is_safe_string_value(key: str | None, value: str) -> bool:
    if not _is_safe_string_field(key) or key is None:
        return False
    normalized = key.casefold().replace("-", "_")
    if normalized == "route":
        return isinstance(value, RouteTemplate)
    if normalized == "event":
        return value in SAFE_LOG_EVENTS
    if normalized == "level":
        return value in {"debug", "info", "warning", "error", "critical"}
    if normalized == "method":
        return value in {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}
    if normalized == "trace_id":
        return TRACE_ID.fullmatch(value) is not None
    if normalized == "span_id":
        return SPAN_ID.fullmatch(value) is not None
    if normalized.endswith("_id") or normalized == "request_id":
        try:
            OpaqueId(value)
        except (TypeError, ValueError):
            return False
        return True
    if normalized.endswith("_version"):
        return VERSION_VALUE.fullmatch(value) is not None
    if normalized.endswith("_code"):
        return value in SAFE_ERROR_CODES
    if normalized in {"result", "state"} or normalized.endswith(("_state", "_status", "_type")):
        return value in SAFE_ENUM_VALUES
    return False


def sanitize_event(value: Any, *, field_name: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED
            if _is_prohibited(str(key))
            else sanitize_event(item, field_name=str(key))
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [sanitize_event(item, field_name=field_name) for item in value]
    if isinstance(value, str):
        return value if _is_safe_string_value(field_name, value) else REDACTED
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return REDACTED


def render_safe_json(_logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]) -> str:
    payload = dict(event_dict)
    context = _LOG_CONTEXT.get()
    if context is not None:
        payload.update({key: value for key, value in asdict(context).items() if value is not None})
    span_context = trace.get_current_span().get_span_context()
    if span_context.is_valid:
        payload.setdefault("trace_id", format(span_context.trace_id, "032x"))
        payload.setdefault("span_id", format(span_context.span_id, "016x"))
    return json.dumps(sanitize_event(payload), ensure_ascii=False, sort_keys=True)


def inject_trace_context(carrier: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Inject the current OpenTelemetry trace into an outbound carrier."""
    propagate.inject(carrier)
    return carrier


def _safe_log_record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _BASE_LOG_RECORD_FACTORY(*args, **kwargs)
    record.msg = REDACTED
    record.args = ()
    record.exc_info = None
    record.exc_text = None
    record.stack_info = None
    return record


def configure_structured_logging(log_level: int = logging.INFO) -> None:
    """Configure structlog so every emitted event passes through the safe renderer."""
    logging.setLogRecordFactory(_safe_log_record_factory)
    structlog.configure(
        processors=[render_safe_json],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
