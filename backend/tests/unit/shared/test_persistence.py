from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from interview_evidence.shared.audit import AuditAppend, AuditResult
from interview_evidence.shared.database import metadata
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.messaging.outbox import AggregateRef, OutboxEvent, OutboxStatus
from interview_evidence.shared.persistence import (
    AuditEventRow,
    OutboxEventRow,
    ProcessedMessageRow,
    SQLAlchemyAuditAppender,
    SQLAlchemyUnitOfWork,
)
from interview_evidence.shared.tenant import (
    ActorType,
    TenantContext,
    TenantContextRequiredError,
    TenantScopeViolation,
)
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 14, 12, 30, tzinfo=UTC)
COMPANY_ID = "0198a82a-0540-7000-8000-000000000001"
OTHER_COMPANY_ID = "0198a82a-0540-7000-8000-000000000002"
EVENT_ID = "0198a82a-0540-7000-8000-000000000006"
AGGREGATE_ID = "0198a82a-0540-7000-8000-000000000007"
CORRELATION_ID = "0198a82a-0540-7000-8000-000000000008"
AUDIT_RESOURCE_ID = "0198a82a-0540-7000-8000-000000000009"


@pytest.fixture
def persistence() -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    try:
        yield engine, factory
    finally:
        metadata.drop_all(engine)
        engine.dispose()


def _context(company_id: str = COMPANY_ID) -> TenantContext:
    return TenantContext(
        company_id=company_id,
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
            aggregate_id=AGGREGATE_ID,
            version=4,
        ),
        "idempotency_key": "outbox-operation-0001",
        "occurred_at": NOW,
        "trace_id": "trace-0001",
        "correlation_id": CORRELATION_ID,
        "causation_id": None,
        "payload": {
            "interview_session_id": AGGREGATE_ID,
            "status": "completed",
        },
    }
    values.update(overrides)
    return OutboxEvent(**values)


def _audit_command(**overrides: object) -> AuditAppend:
    values: dict[str, object] = {
        "action": "report.view",
        "resource_type": "report",
        "resource_id": AUDIT_RESOURCE_ID,
        "result": AuditResult.SUCCESS,
        "metadata": {"report_version": 1, "status": "ready"},
        "idempotency_key": "audit-operation-0001",
    }
    values.update(overrides)
    return AuditAppend(**values)


def _uow(factory: sessionmaker[Session]) -> SQLAlchemyUnitOfWork:
    clock = FixedClock(NOW)
    return SQLAlchemyUnitOfWork(
        factory,
        clock=clock,
        id_generator=UUID7Generator(clock, randbytes=lambda size: b"\x00" * size),
    )


def test_shared_rows_have_tenant_scoped_primary_and_idempotency_constraints() -> None:
    assert {
        OutboxEventRow.__tablename__,
        ProcessedMessageRow.__tablename__,
        AuditEventRow.__tablename__,
    } == {
        "outbox_events",
        "processed_messages",
        "audit_events",
    }

    for row_type in (OutboxEventRow, ProcessedMessageRow, AuditEventRow):
        primary_key = {column.name for column in row_type.__table__.primary_key.columns}
        assert "company_id" in primary_key

    outbox_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in OutboxEventRow.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    processed_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in ProcessedMessageRow.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }
    audit_uniques = {
        tuple(column.name for column in constraint.columns)
        for constraint in AuditEventRow.__table__.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    }

    assert ("company_id", "idempotency_key") in outbox_uniques
    assert ("company_id", "consumer_name", "event_id", "event_version") in processed_uniques
    assert ("company_id", "consumer_name", "idempotency_key") in processed_uniques
    assert ("company_id", "idempotency_key") in audit_uniques


def test_uow_commits_outbox_and_audit_atomically_and_rolls_back_by_default(
    persistence: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = persistence

    with _uow(factory) as uow:
        uow.outbox.add(_context(), _event())
        uow.audit_events.append(_context(), _audit_command())

    with factory() as session:
        assert session.scalar(select(OutboxEventRow)) is None
        assert session.scalar(select(AuditEventRow)) is None

    with _uow(factory) as uow:
        uow.outbox.add(_context(), _event())
        uow.audit_events.append(_context(), _audit_command())
        uow.commit()

    with factory() as session:
        stored_outbox = session.scalar(select(OutboxEventRow))
        stored_audit = session.scalar(select(AuditEventRow))
        assert stored_outbox is not None
        assert stored_outbox.payload == {
            "interview_session_id": AGGREGATE_ID,
            "status": "completed",
        }
        assert "completed" not in repr(stored_outbox)
        assert stored_audit is not None
        assert stored_audit.metadata_payload == {"report_version": 1, "status": "ready"}
        assert "ready" not in repr(stored_audit)


def test_durable_outbox_tracks_attempts_publication_and_tenant_scope(
    persistence: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = persistence

    with _uow(factory) as uow:
        uow.outbox.add(_context(), _event())
        uow.commit()

    with _uow(factory) as uow:
        attempted = uow.outbox.record_attempt(
            _context(), EVENT_ID, failure_code="DEPENDENCY_TIMEOUT"
        )
        assert attempted.status is OutboxStatus.RETRYING
        assert attempted.attempt_count == 1
        assert attempted.last_failure_code == "DEPENDENCY_TIMEOUT"
        uow.commit()

    with _uow(factory) as uow:
        current = uow.outbox.add(_context(), _event())
        assert current.status is OutboxStatus.RETRYING
        published = uow.outbox.mark_published(
            _context(), EVENT_ID, published_at=NOW + timedelta(seconds=5)
        )
        assert published.status is OutboxStatus.PUBLISHED
        assert published.attempt_count == 1
        assert uow.outbox.pending(_context()) == ()
        assert uow.outbox.pending(_context(OTHER_COMPANY_ID)) == ()
        with pytest.raises(SafeApplicationError) as missing:
            uow.outbox.mark_published(_context(OTHER_COMPANY_ID), EVENT_ID, published_at=NOW)
        assert missing.value.code is ErrorCode.RESOURCE_NOT_FOUND
        uow.commit()

    with _uow(factory) as uow:
        assert uow.outbox.get(_context(), EVENT_ID).status is OutboxStatus.PUBLISHED
        with pytest.raises(TenantContextRequiredError):
            uow.outbox.pending(None)  # type: ignore[arg-type]


def test_durable_processed_message_recording_is_idempotent_and_tenant_mandatory(
    persistence: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = persistence
    first_processed_at = NOW

    with _uow(factory) as uow:
        first = uow.processed_messages.record_outcome(
            _context(),
            consumer_name="reporting.interview_completed",
            event_id=EVENT_ID,
            event_version=1,
            idempotency_key="outbox-operation-0001",
            first_processed_at=first_processed_at,
            outcome={"report_version": 1, "status": "accepted"},
        )
        duplicate = uow.processed_messages.record_outcome(
            _context(),
            consumer_name="reporting.interview_completed",
            event_id=EVENT_ID,
            event_version=1,
            idempotency_key="outbox-operation-0001",
            first_processed_at=first_processed_at + timedelta(seconds=30),
            outcome={"status": "accepted", "report_version": 1},
        )
        assert duplicate == first

        with pytest.raises(SafeApplicationError) as conflict:
            uow.processed_messages.record_outcome(
                _context(),
                consumer_name="reporting.interview_completed",
                event_id=EVENT_ID,
                event_version=1,
                idempotency_key="outbox-operation-0001",
                first_processed_at=first_processed_at,
                outcome={"status": "rejected"},
            )
        assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT

        with pytest.raises(TenantScopeViolation):
            uow.processed_messages.record_outcome(
                _context(OTHER_COMPANY_ID),
                consumer_name="reporting.interview_completed",
                event_id=EVENT_ID,
                event_version=1,
                idempotency_key="outbox-operation-0001",
                first_processed_at=first_processed_at,
                outcome={"status": "accepted"},
                company_id=COMPANY_ID,
            )
        uow.commit()

    with factory() as session:
        assert len(session.scalars(select(ProcessedMessageRow)).all()) == 1


@pytest.mark.asyncio
async def test_durable_audit_appender_is_secret_safe_idempotent_and_tenant_scoped(
    persistence: tuple[Engine, sessionmaker[Session]],
) -> None:
    _, factory = persistence
    clock = FixedClock(NOW)
    appender = SQLAlchemyAuditAppender(
        factory,
        clock=clock,
        id_generator=UUID7Generator(clock, randbytes=lambda size: b"\x01" * size),
    )

    first = await appender.append(_context(), _audit_command())
    duplicate = await appender.append(_context(), _audit_command())
    assert duplicate == first
    assert first.company_id == COMPANY_ID
    assert first.actor_id == _context().actor_id
    assert first.request_id == _context().request_id

    with pytest.raises(SafeApplicationError) as conflict:
        await appender.append(
            _context(),
            _audit_command(metadata={"report_version": 2, "status": "ready"}),
        )
    assert conflict.value.code is ErrorCode.IDEMPOTENCY_CONFLICT
    assert await appender.list_for_tenant(_context(OTHER_COMPANY_ID)) == ()
    with pytest.raises(TenantScopeViolation):
        await appender.get(_context(OTHER_COMPANY_ID), first.audit_event_id)
