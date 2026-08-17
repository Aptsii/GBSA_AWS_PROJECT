from __future__ import annotations

import json
from datetime import UTC, datetime
from threading import Event

from interview_evidence.shared.database import metadata
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock
from interview_evidence.shared.metrics import (
    InMemoryMetricSink,
    MetricName,
    MetricUnit,
    OperationalMetrics,
)
from interview_evidence.shared.persistence import ProcessedMessageRow
from interview_evidence.shared.tenant import TenantContext
from interview_evidence.workers.__main__ import QueueEvent, QueueWorker
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = "018f2000-0000-7000-8000-000000000100"
EVENT_ID = "018f2000-0000-7000-8000-000000000500"
CORRELATION_ID = "018f2000-0000-7000-8000-000000000501"
AGGREGATE_ID = "018f2000-0000-7000-8000-000000000510"


class _FakeSQS:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.messages = messages
        self.deleted: list[str] = []
        self.visibility: list[tuple[str, int]] = []
        self.dead_letters: list[dict[str, object]] = []

    def receive_message(self, **arguments: object) -> dict[str, object]:
        del arguments
        messages, self.messages = self.messages, []
        return {"Messages": messages}

    def delete_message(self, **arguments: object) -> None:
        self.deleted.append(str(arguments["ReceiptHandle"]))

    def change_message_visibility(self, **arguments: object) -> None:
        self.visibility.append(
            (str(arguments["ReceiptHandle"]), int(arguments["VisibilityTimeout"]))
        )

    def send_message(self, **arguments: object) -> None:
        self.dead_letters.append(arguments)


class _Handler:
    def __init__(
        self,
        failure: SafeApplicationError | None = None,
        outcome: dict[str, object] | None = None,
    ) -> None:
        self.failure = failure
        self.outcome = outcome or {"status": "succeeded"}
        self.events: list[tuple[TenantContext, QueueEvent]] = []

    def handle_event(
        self,
        context: TenantContext,
        event: QueueEvent,
    ) -> dict[str, object]:
        self.events.append((context, event))
        if self.failure is not None:
            raise self.failure
        return self.outcome


def _message(
    *,
    receive_count: int = 1,
    event_version: int = 1,
    occurred_at: str = "2026-08-17T08:59:55Z",
    sent_timestamp_ms: int = 1_786_957_198_000,
) -> dict[str, object]:
    return {
        "MessageId": EVENT_ID,
        "ReceiptHandle": f"receipt-{receive_count}",
        "Attributes": {
            "ApproximateReceiveCount": str(receive_count),
            "SentTimestamp": str(sent_timestamp_ms),
        },
        "Body": json.dumps(
            {
                "event_id": EVENT_ID,
                "event_type": "submission.analysis_requested",
                "event_version": event_version,
                "occurred_at": occurred_at,
                "company_id": COMPANY_ID,
                "aggregate": {
                    "type": "submission",
                    "id": AGGREGATE_ID,
                    "version": 1,
                },
                "idempotency_key": "analysis-request-0001",
                "trace_id": "worker-test",
                "correlation_id": CORRELATION_ID,
                "causation_id": None,
                "payload": {"submission_id": AGGREGATE_ID, "analysis_version": 1},
            }
        ),
    }


def _session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _worker(
    sqs: _FakeSQS,
    handler: _Handler,
    factory: sessionmaker[Session],
    metrics: OperationalMetrics | None = None,
) -> QueueWorker:
    return QueueWorker(
        sqs=sqs,
        queue_url="https://sqs.example.test/source",
        dlq_url="https://sqs.example.test/dlq",
        registry={"submission.analysis_requested": handler},
        session_factory=factory,
        clock=FixedClock(NOW),
        max_attempts=3,
        wait_time_seconds=0,
        metrics=metrics,
    )


def test_successful_delivery_records_outcome_then_acknowledges() -> None:
    factory = _session_factory()
    sqs = _FakeSQS([_message()])
    handler = _Handler()

    processed = _worker(sqs, handler, factory).run_once()

    assert processed == 1
    assert len(handler.events) == 1
    context, event = handler.events[0]
    assert str(context.company_id) == COMPANY_ID
    assert event.event_version == 1
    assert sqs.deleted == ["receipt-1"]
    with factory() as session:
        assert len(session.scalars(select(ProcessedMessageRow)).all()) == 1


def test_duplicate_delivery_is_acknowledged_without_reinvoking_handler() -> None:
    factory = _session_factory()
    handler = _Handler()
    first = _FakeSQS([_message(receive_count=1)])
    second = _FakeSQS([_message(receive_count=2)])

    _worker(first, handler, factory).run_once()
    _worker(second, handler, factory).run_once()

    assert len(handler.events) == 1
    assert second.deleted == ["receipt-2"]


def test_retryable_failure_extends_visibility_without_acknowledging() -> None:
    factory = _session_factory()
    sqs = _FakeSQS([_message(receive_count=2)])
    handler = _Handler(SafeApplicationError(ErrorCode.DEPENDENCY_TIMEOUT))

    _worker(sqs, handler, factory).run_once()

    assert sqs.deleted == []
    assert sqs.dead_letters == []
    assert sqs.visibility == [("receipt-2", 4)]


def test_worker_boundary_records_queue_reconciliation_degraded_and_stage_metrics() -> None:
    factory = _session_factory()
    sqs = _FakeSQS([_message()])
    sink = InMemoryMetricSink()
    metrics = OperationalMetrics(sink, clock=FixedClock(NOW))
    handler = _Handler(outcome={"status": "succeeded", "degraded_mode": "search_fallback"})

    _worker(sqs, handler, factory, metrics).run_once()

    by_name = {metric.name: metric for metric in sink.metrics}
    assert by_name[MetricName.QUEUE_AGE].value == 2.0
    assert by_name[MetricName.QUEUE_AGE].unit is MetricUnit.SECONDS
    assert by_name[MetricName.RECONCILIATION_LAG].value == 5_000
    assert by_name[MetricName.DEGRADED_MODE].mode == "search_fallback"
    assert by_name[MetricName.STAGE_LATENCY].operation_version == "event-v1"


def test_worker_retry_action_emits_versioned_retry_metric() -> None:
    factory = _session_factory()
    sqs = _FakeSQS([_message(receive_count=2)])
    sink = InMemoryMetricSink()
    metrics = OperationalMetrics(sink, clock=FixedClock(NOW))
    handler = _Handler(SafeApplicationError(ErrorCode.DEPENDENCY_TIMEOUT))

    _worker(sqs, handler, factory, metrics).run_once()

    retry = next(metric for metric in sink.metrics if metric.name is MetricName.RETRY)
    assert retry.stage == "submission.analysis_requested"
    assert retry.operation_version == "event-v1"


def test_exhausted_or_unsupported_delivery_moves_to_dlq_and_acks() -> None:
    factory = _session_factory()
    exhausted_sqs = _FakeSQS([_message(receive_count=3)])
    exhausted_handler = _Handler(SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE))
    unsupported_sqs = _FakeSQS([_message(event_version=2)])

    _worker(exhausted_sqs, exhausted_handler, factory).run_once()
    _worker(unsupported_sqs, _Handler(), factory).run_once()

    assert exhausted_sqs.deleted == ["receipt-3"]
    assert len(exhausted_sqs.dead_letters) == 1
    assert unsupported_sqs.deleted == ["receipt-1"]
    assert len(unsupported_sqs.dead_letters) == 1


def test_shutdown_event_stops_before_another_receive() -> None:
    factory = _session_factory()
    sqs = _FakeSQS([_message()])
    shutdown = Event()
    shutdown.set()

    _worker(sqs, _Handler(), factory).run(shutdown)

    assert len(sqs.messages) == 1
