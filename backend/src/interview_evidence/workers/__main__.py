"""Tenant-scoped SQS worker with durable duplicate detection and bounded retries."""

from __future__ import annotations

import json
import os
import re
import signal
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from time import perf_counter
from typing import Protocol

import boto3  # type: ignore[import-untyped]
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from interview_evidence.main import _create_object_storage, create_worker_registry
from interview_evidence.shared.config import Settings
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock
from interview_evidence.shared.metrics import (
    MetricBoundary,
    OperationalMetrics,
    extract_operational_signals,
)
from interview_evidence.shared.persistence import SQLAlchemyProcessedMessageStore
from interview_evidence.shared.tenant import ActorType, TenantContext

_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
_TRACE_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_PROHIBITED_PAYLOAD_KEYS = frozenset(
    {
        "answer",
        "answer_text",
        "authorization",
        "credential",
        "document_text",
        "password",
        "raw_text",
        "secret",
        "signed_url",
        "source_text",
        "token",
        "transcript",
        "transcript_text",
    }
)
_RETRYABLE_CODES = frozenset(
    {
        ErrorCode.DEPENDENCY_TIMEOUT,
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        ErrorCode.RATE_LIMITED,
    }
)


class SQSClient(Protocol):
    def receive_message(self, **arguments: object) -> dict[str, object]: ...

    def delete_message(self, **arguments: object) -> object: ...

    def change_message_visibility(self, **arguments: object) -> object: ...

    def send_message(self, **arguments: object) -> object: ...


class EventHandler(Protocol):
    def handle_event(
        self,
        context: TenantContext,
        event: QueueEvent,
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class QueueEvent:
    event_id: OpaqueId
    event_type: str
    event_version: int
    occurred_at: datetime
    company_id: OpaqueId
    aggregate_type: str
    aggregate_id: OpaqueId
    aggregate_version: int
    idempotency_key: str
    trace_id: str
    correlation_id: OpaqueId
    causation_id: OpaqueId | None
    payload: Mapping[str, object]

    @classmethod
    def from_body(cls, body: str) -> QueueEvent:
        try:
            value = json.loads(body)
        except json.JSONDecodeError:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None
        if not isinstance(value, dict):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        aggregate = value.get("aggregate")
        payload = value.get("payload")
        if not isinstance(aggregate, dict) or not isinstance(payload, dict):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        event_type = value.get("event_type")
        trace_id = value.get("trace_id")
        idempotency_key = value.get("idempotency_key")
        if not isinstance(event_type, str) or _EVENT_TYPE.fullmatch(event_type) is None:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if not isinstance(trace_id, str) or _TRACE_ID.fullmatch(trace_id) is None:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if not isinstance(idempotency_key, str) or not 16 <= len(idempotency_key) <= 128:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        if _contains_prohibited_key(payload):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        try:
            occurred_at = datetime.fromisoformat(str(value["occurred_at"]).replace("Z", "+00:00"))
            if occurred_at.tzinfo is None:
                raise ValueError("event time must be timezone-aware")
            causation_value = value.get("causation_id")
            return cls(
                event_id=OpaqueId(str(value["event_id"])),
                event_type=event_type,
                event_version=_positive_int(value["event_version"]),
                occurred_at=occurred_at.astimezone(UTC),
                company_id=OpaqueId(str(value["company_id"])),
                aggregate_type=_safe_code(aggregate["type"]),
                aggregate_id=OpaqueId(str(aggregate["id"])),
                aggregate_version=_positive_int(aggregate["version"]),
                idempotency_key=idempotency_key,
                trace_id=trace_id,
                correlation_id=OpaqueId(str(value["correlation_id"])),
                causation_id=(
                    OpaqueId(str(causation_value)) if causation_value is not None else None
                ),
                payload=dict(payload),
            )
        except (KeyError, TypeError, ValueError):
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None

    def context(self) -> TenantContext:
        return TenantContext(
            company_id=self.company_id,
            actor_type=ActorType.SYSTEM,
            actor_id=self.event_id,
            request_id=self.correlation_id,
            trace_id=self.trace_id,
        )

    def as_mapping(self) -> dict[str, object]:
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at.isoformat().replace("+00:00", "Z"),
            "company_id": str(self.company_id),
            "aggregate": {
                "type": self.aggregate_type,
                "id": str(self.aggregate_id),
                "version": self.aggregate_version,
            },
            "idempotency_key": self.idempotency_key,
            "trace_id": self.trace_id,
            "correlation_id": str(self.correlation_id),
            "causation_id": str(self.causation_id) if self.causation_id is not None else None,
            "payload": dict(self.payload),
        }


class QueueWorker:
    def __init__(
        self,
        *,
        sqs: SQSClient,
        queue_url: str,
        dlq_url: str,
        registry: Mapping[str, object],
        session_factory: sessionmaker[Session],
        clock: Clock | None = None,
        max_attempts: int = 5,
        wait_time_seconds: int = 20,
        visibility_timeout_seconds: int = 60,
        metrics: OperationalMetrics | None = None,
        monotonic: Callable[[], float] = perf_counter,
    ) -> None:
        if not queue_url or not dlq_url:
            raise ValueError("source queue and DLQ URLs are required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not 0 <= wait_time_seconds <= 20:
            raise ValueError("wait_time_seconds must be between 0 and 20")
        if visibility_timeout_seconds < 1:
            raise ValueError("visibility timeout must be positive")
        self._sqs = sqs
        self._queue_url = queue_url
        self._dlq_url = dlq_url
        self._registry = registry
        self._session_factory = session_factory
        self._clock = clock or SystemClock()
        self._max_attempts = max_attempts
        self._wait_time_seconds = wait_time_seconds
        self._visibility_timeout_seconds = visibility_timeout_seconds
        self._metrics = metrics or OperationalMetrics(clock=self._clock)
        self._monotonic = monotonic

    def run(self, shutdown: Event) -> None:
        while not shutdown.is_set():
            try:
                processed = self.run_once()
            except Exception:
                sys.stderr.write("Worker receive failed; retrying.\n")
                shutdown.wait(1)
                continue
            if processed == 0:
                shutdown.wait(0.1)

    def run_once(self) -> int:
        response = self._sqs.receive_message(
            QueueUrl=self._queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=self._wait_time_seconds,
            VisibilityTimeout=self._visibility_timeout_seconds,
            AttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
            MessageAttributeNames=["All"],
        )
        messages = response.get("Messages", [])
        if not isinstance(messages, list):
            raise RuntimeError("SQS Messages response must be a list")
        for message in messages:
            if not isinstance(message, dict):
                continue
            self._process_message(message)
        return len(messages)

    def _process_message(self, message: dict[str, object]) -> None:
        started_at = self._monotonic()
        receipt_handle = str(message.get("ReceiptHandle", ""))
        body = message.get("Body")
        receive_count = _receive_count(message)
        event: QueueEvent | None = None
        result = "failed"
        if not receipt_handle or not isinstance(body, str):
            self._dead_letter(message, "INVALID_REQUEST", receive_count)
        else:
            try:
                event = QueueEvent.from_body(body)
                stage = event.event_type
                operation_version = f"event-v{event.event_version}"
                self._metrics.record_queue_age(
                    stage=stage,
                    operation_version=operation_version,
                    age_ms=_queue_age_ms(message, self._clock.now(), event.occurred_at),
                )
                if event.event_version != 1:
                    raise UnsupportedEventVersion
                handler = self._registry.get(event.event_type)
                if handler is None:
                    raise UnsupportedEventType
                context = event.context()
                outcome: Mapping[str, object] | None = None
                with self._session_factory() as session:
                    store = SQLAlchemyProcessedMessageStore(session)
                    existing = store.find(
                        context,
                        consumer_name=event.event_type,
                        event_id=event.event_id,
                        event_version=event.event_version,
                        idempotency_key=event.idempotency_key,
                    )
                    if existing is None:
                        outcome = _invoke_handler(handler, context, event)
                        store.record_outcome(
                            context,
                            consumer_name=event.event_type,
                            event_id=event.event_id,
                            event_version=event.event_version,
                            idempotency_key=event.idempotency_key,
                            first_processed_at=self._clock.now(),
                            outcome=outcome,
                        )
                        session.commit()
                self._ack(receipt_handle)
                result = "succeeded"
                self._metrics.record_reconciliation_lag(
                    boundary=MetricBoundary.WORKER,
                    stage=stage,
                    operation_version=operation_version,
                    lag_ms=_elapsed_ms(event.occurred_at, self._clock.now()),
                )
                if outcome is not None:
                    for mode in extract_operational_signals(outcome).degraded_modes:
                        self._metrics.record_degraded_mode(
                            boundary=MetricBoundary.WORKER,
                            stage=stage,
                            operation_version=operation_version,
                            mode=mode,
                        )
            except SafeApplicationError as error:
                if error.code in _RETRYABLE_CODES and receive_count < self._max_attempts:
                    self._record_retry(event)
                    self._retry(receipt_handle, receive_count)
                else:
                    self._dead_letter(message, error.code.value, receive_count)
            except (UnsupportedEventType, UnsupportedEventVersion):
                self._dead_letter(message, "UNSUPPORTED_EVENT", receive_count)
            except Exception:
                if receive_count < self._max_attempts:
                    self._record_retry(event)
                    self._retry(receipt_handle, receive_count)
                else:
                    self._dead_letter(message, ErrorCode.INTERNAL_ERROR.value, receive_count)
        self._metrics.record_stage_latency(
            boundary=MetricBoundary.WORKER,
            stage=event.event_type if event is not None else "queue_message",
            operation_version=f"event-v{event.event_version}" if event is not None else "event-v0",
            elapsed_ms=max(0.0, (self._monotonic() - started_at) * 1000),
            result=result,
        )

    def _record_retry(self, event: QueueEvent | None) -> None:
        self._metrics.record_retry(
            boundary=MetricBoundary.WORKER,
            stage=event.event_type if event is not None else "queue_message",
            operation_version=f"event-v{event.event_version}" if event is not None else "event-v0",
        )

    def _retry(self, receipt_handle: str, receive_count: int) -> None:
        delay = min(900, max(1, 2**receive_count))
        self._sqs.change_message_visibility(
            QueueUrl=self._queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=delay,
        )

    def _dead_letter(
        self,
        message: Mapping[str, object],
        failure_code: str,
        receive_count: int,
    ) -> None:
        body = message.get("Body")
        receipt_handle = str(message.get("ReceiptHandle", ""))
        if not isinstance(body, str) or not receipt_handle:
            return
        self._sqs.send_message(
            QueueUrl=self._dlq_url,
            MessageBody=body,
            MessageAttributes={
                "failure_code": {"DataType": "String", "StringValue": failure_code},
                "receive_count": {"DataType": "Number", "StringValue": str(receive_count)},
            },
        )
        self._ack(receipt_handle)

    def _ack(self, receipt_handle: str) -> None:
        self._sqs.delete_message(
            QueueUrl=self._queue_url,
            ReceiptHandle=receipt_handle,
        )


class UnsupportedEventType(Exception):
    pass


class UnsupportedEventVersion(Exception):
    pass


def _invoke_handler(
    handler: object,
    context: TenantContext,
    event: QueueEvent,
) -> Mapping[str, object]:
    callback = getattr(handler, "handle_event", None)
    if not callable(callback):
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
    outcome = callback(context, event)
    if not isinstance(outcome, Mapping):
        raise SafeApplicationError(ErrorCode.INTERNAL_ERROR)
    return outcome


def _contains_prohibited_key(value: Mapping[str, object]) -> bool:
    for key, item in value.items():
        if key.casefold().replace("-", "_") in _PROHIBITED_PAYLOAD_KEYS:
            return True
        if isinstance(item, Mapping) and _contains_prohibited_key(item):
            return True
        if isinstance(item, list):
            for nested in item:
                if isinstance(nested, Mapping) and _contains_prohibited_key(nested):
                    return True
    return False


def _positive_int(value: object) -> int:
    if not isinstance(value, int) or value < 1:
        raise ValueError("value must be a positive integer")
    return value


def _safe_code(value: object) -> str:
    if not isinstance(value, str) or _TRACE_ID.fullmatch(value) is None:
        raise ValueError("value must be a safe code")
    return value


def _receive_count(message: Mapping[str, object]) -> int:
    attributes = message.get("Attributes")
    if not isinstance(attributes, Mapping):
        return 1
    try:
        return max(1, int(str(attributes.get("ApproximateReceiveCount", "1"))))
    except ValueError:
        return 1


def _queue_age_ms(
    message: Mapping[str, object],
    now: datetime,
    fallback: datetime,
) -> float:
    attributes = message.get("Attributes")
    if isinstance(attributes, Mapping):
        try:
            sent_at_ms = int(str(attributes.get("SentTimestamp", "")))
        except ValueError:
            sent_at_ms = -1
        if sent_at_ms >= 0:
            return max(0.0, (now.timestamp() * 1000) - sent_at_ms)
    return _elapsed_ms(fallback, now)


def _elapsed_ms(started_at: datetime, completed_at: datetime) -> float:
    return max(0.0, (completed_at - started_at).total_seconds() * 1000)


def main() -> int:
    settings = Settings()  # type: ignore[call-arg]
    if settings.event_queue_url is None or settings.event_dlq_url is None:
        sys.stderr.write("Worker queue and DLQ URLs are required.\n")
        return 2
    engine = create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)
    factory = sessionmaker(engine, expire_on_commit=False)
    registry = create_worker_registry(
        session_factory=factory,
        object_storage=_create_object_storage(settings),
    )
    if not registry:
        sys.stderr.write("No worker handlers are registered.\n")
        return 2
    sqs = boto3.client(
        "sqs",
        region_name=settings.aws_region,
        endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
    )
    worker = QueueWorker(
        sqs=sqs,
        queue_url=settings.event_queue_url.get_secret_value(),
        dlq_url=settings.event_dlq_url.get_secret_value(),
        registry=registry,
        session_factory=factory,
        max_attempts=settings.worker_max_attempts,
        wait_time_seconds=settings.worker_wait_time_seconds,
        visibility_timeout_seconds=settings.worker_visibility_timeout_seconds,
    )
    shutdown = Event()

    def stop(_signal_number: int, _frame: object) -> None:
        shutdown.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    worker.run(shutdown)
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
