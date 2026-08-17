from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.messaging.outbox import (
    AggregateRef,
    InMemoryOutbox,
    InMemoryProcessedMessageStore,
    OutboxEvent,
    OutboxStatus,
    ProcessedMessage,
)
from interview_evidence.shared.tenant import ActorType, TenantContext

NOW = datetime(2026, 8, 14, 12, 30, tzinfo=UTC)
COMPANY_ID = "0198a82a-0540-7000-8000-000000000001"
EVENT_ID = "0198a82a-0540-7000-8000-000000000006"


def _context() -> TenantContext:
    return TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.SYSTEM,
        actor_id="0198a82a-0540-7000-8000-000000000003",
        request_id="0198a82a-0540-7000-8000-000000000005",
        trace_id="trace-0001",
    )


def _event(**overrides: object) -> OutboxEvent:
    values: dict[str, object] = {
        "event_id": EVENT_ID,
        "company_id": COMPANY_ID,
        "event_type": "interview.completed",
        "event_version": 1,
        "aggregate": AggregateRef(
            aggregate_type="interview_session",
            aggregate_id="0198a82a-0540-7000-8000-000000000007",
            version=4,
        ),
        "idempotency_key": "outbox-operation-0001",
        "occurred_at": NOW,
        "trace_id": "trace-0001",
        "correlation_id": "0198a82a-0540-7000-8000-000000000008",
        "causation_id": None,
        "payload": {
            "interview_session_id": "0198a82a-0540-7000-8000-000000000007",
            "status": "completed",
        },
    }
    values.update(overrides)
    return OutboxEvent(**values)


def test_outbox_event_is_immutable_sanitized_and_has_pure_state_transitions() -> None:
    event = _event()
    attempted = event.record_attempt("DEPENDENCY_TIMEOUT")
    published = attempted.mark_published(NOW)

    assert event.status is OutboxStatus.PENDING
    assert event.attempt_count == 0
    assert attempted.status is OutboxStatus.RETRYING
    assert attempted.attempt_count == 1
    assert published.status is OutboxStatus.PUBLISHED
    assert published.published_at == NOW

    with pytest.raises(TypeError):
        event.payload["status"] = "changed"  # type: ignore[index]
    with pytest.raises(ValueError, match="prohibited"):
        _event(payload={"answer_text": "지원자 답변 원문"})
    with pytest.raises(ValueError, match=r"secret-shaped|token-shaped"):
        _event(payload={"status": "RAWACCESSTOKEN1234567890ABCDEFG"})


def test_outbox_store_returns_original_for_exact_retry_and_rejects_conflict() -> None:
    store = InMemoryOutbox()
    event = _event()

    assert store.add(_context(), event) is event
    assert store.add(_context(), event) is event
    assert len(store.pending(_context())) == 1

    with pytest.raises(SafeApplicationError) as conflict:
        store.add(
            _context(),
            _event(event_id="0198a82a-0540-7000-8000-000000000099"),
        )
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT


def test_processed_message_store_preserves_duplicate_result_and_digest() -> None:
    processed = ProcessedMessage.from_outcome(
        company_id=COMPANY_ID,
        consumer_name="reporting.interview_completed",
        event_id=EVENT_ID,
        event_version=1,
        idempotency_key="outbox-operation-0001",
        first_processed_at=NOW,
        outcome={"status": "accepted", "report_version": 1},
    )
    duplicate = ProcessedMessage.from_outcome(
        company_id=COMPANY_ID,
        consumer_name="reporting.interview_completed",
        event_id=EVENT_ID,
        event_version=1,
        idempotency_key="outbox-operation-0001",
        first_processed_at=NOW,
        outcome={"report_version": 1, "status": "accepted"},
    )
    store = InMemoryProcessedMessageStore()

    assert processed.outcome_digest == duplicate.outcome_digest
    assert store.record(_context(), processed) is processed
    assert store.record(_context(), duplicate) is processed

    conflicting = ProcessedMessage.from_outcome(
        company_id=COMPANY_ID,
        consumer_name="reporting.interview_completed",
        event_id=EVENT_ID,
        event_version=1,
        idempotency_key="outbox-operation-0001",
        first_processed_at=NOW,
        outcome={"status": "rejected"},
    )
    with pytest.raises(SafeApplicationError):
        store.record(_context(), conflicting)
