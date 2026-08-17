"""Tenant-scoped SQLAlchemy persistence for shared technical primitives."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast

from interview_evidence.shared._validation import FrozenValue, plain_operational_payload
from interview_evidence.shared.audit import AuditAppend, AuditEvent, AuditResult
from interview_evidence.shared.database import Base
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.messaging.outbox import (
    AggregateRef,
    OutboxEvent,
    OutboxStatus,
    ProcessedMessage,
)
from interview_evidence.shared.tenant import (
    ActorType,
    TenantContext,
    TenantScopeViolation,
    ensure_company_scope,
    require_tenant_context,
)
from sqlalchemy import JSON, DateTime, Integer, String, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"
    __table_args__ = (UniqueConstraint("company_id", "idempotency_key"),)

    company_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(128), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    causation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return (
            "OutboxEventRow("
            f"company_id={self.company_id!r}, event_id={self.event_id!r}, "
            f"status={self.status!r}, attempt_count={self.attempt_count})"
        )


class ProcessedMessageRow(Base):
    __tablename__ = "processed_messages"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "consumer_name",
            "event_id",
            "event_version",
            name="uq_processed_messages_event",
        ),
        UniqueConstraint(
            "company_id",
            "consumer_name",
            "idempotency_key",
            name="uq_processed_messages_idempotency",
        ),
    )

    company_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    first_processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    outcome_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:
        return (
            "ProcessedMessageRow("
            f"company_id={self.company_id!r}, consumer_name={self.consumer_name!r}, "
            f"event_id={self.event_id!r}, event_version={self.event_version})"
        )


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (UniqueConstraint("company_id", "idempotency_key"),)

    company_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    audit_event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False)
    result: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    command_digest: Mapped[str] = mapped_column(String(64), nullable=False)

    def __repr__(self) -> str:
        return (
            "AuditEventRow("
            f"company_id={self.company_id!r}, audit_event_id={self.audit_event_id!r}, "
            f"action={self.action!r}, result={self.result!r})"
        )


class SQLAlchemyOutbox:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, context: TenantContext, event: OutboxEvent) -> OutboxEvent:
        ensure_company_scope(context, event.company_id)
        by_event = self._session.scalar(
            select(OutboxEventRow).where(
                OutboxEventRow.company_id == str(event.company_id),
                OutboxEventRow.event_id == str(event.event_id),
            )
        )
        by_idempotency = self._session.scalar(
            select(OutboxEventRow).where(
                OutboxEventRow.company_id == str(event.company_id),
                OutboxEventRow.idempotency_key == event.idempotency_key,
            )
        )
        existing = by_event or by_idempotency
        if existing is not None:
            stored = _outbox_event(existing)
            if _outbox_identity(stored) != _outbox_identity(event):
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return stored

        row = OutboxEventRow(
            company_id=str(event.company_id),
            event_id=str(event.event_id),
            event_type=event.event_type,
            event_version=event.event_version,
            aggregate_type=event.aggregate.aggregate_type,
            aggregate_id=str(event.aggregate.aggregate_id),
            aggregate_version=event.aggregate.version,
            idempotency_key=event.idempotency_key,
            occurred_at=event.occurred_at,
            trace_id=event.trace_id,
            correlation_id=str(event.correlation_id),
            causation_id=str(event.causation_id) if event.causation_id is not None else None,
            payload=plain_operational_payload(event.payload),
            status=event.status.value,
            attempt_count=event.attempt_count,
            last_failure_code=event.last_failure_code,
            published_at=event.published_at,
        )
        self._session.add(row)
        self._session.flush()
        return _outbox_event(row)

    def get(self, context: TenantContext, event_id: str | OpaqueId) -> OutboxEvent:
        checked = require_tenant_context(context)
        row = self._session.scalar(
            select(OutboxEventRow).where(
                OutboxEventRow.company_id == str(checked.company_id),
                OutboxEventRow.event_id == str(OpaqueId(event_id)),
            )
        )
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        return _outbox_event(row)

    def pending(self, context: TenantContext) -> tuple[OutboxEvent, ...]:
        checked = require_tenant_context(context)
        rows = self._session.scalars(
            select(OutboxEventRow)
            .where(
                OutboxEventRow.company_id == str(checked.company_id),
                OutboxEventRow.status != OutboxStatus.PUBLISHED.value,
            )
            .order_by(OutboxEventRow.occurred_at, OutboxEventRow.event_id)
        ).all()
        return tuple(_outbox_event(row) for row in rows)

    def record_attempt(
        self,
        context: TenantContext,
        event_id: str | OpaqueId,
        *,
        failure_code: str,
    ) -> OutboxEvent:
        current = self.get(context, event_id)
        updated = current.record_attempt(failure_code)
        row = self._required_row(context, event_id)
        _apply_outbox_state(row, updated)
        self._session.flush()
        return updated

    def mark_published(
        self,
        context: TenantContext,
        event_id: str | OpaqueId,
        *,
        published_at: datetime,
    ) -> OutboxEvent:
        current = self.get(context, event_id)
        updated = current.mark_published(published_at)
        row = self._required_row(context, event_id)
        _apply_outbox_state(row, updated)
        self._session.flush()
        return updated

    def _required_row(
        self,
        context: TenantContext,
        event_id: str | OpaqueId,
    ) -> OutboxEventRow:
        checked = require_tenant_context(context)
        row = self._session.scalar(
            select(OutboxEventRow).where(
                OutboxEventRow.company_id == str(checked.company_id),
                OutboxEventRow.event_id == str(OpaqueId(event_id)),
            )
        )
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        return row


class SQLAlchemyProcessedMessageStore:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record_outcome(
        self,
        context: TenantContext,
        *,
        consumer_name: str,
        event_id: str | OpaqueId,
        event_version: int,
        idempotency_key: str,
        first_processed_at: datetime,
        outcome: Mapping[str, object],
        company_id: str | OpaqueId | None = None,
    ) -> ProcessedMessage:
        checked = require_tenant_context(context)
        scoped_company_id = OpaqueId(company_id or checked.company_id)
        ensure_company_scope(checked, scoped_company_id)
        message = ProcessedMessage.from_outcome(
            company_id=scoped_company_id,
            consumer_name=consumer_name,
            event_id=event_id,
            event_version=event_version,
            idempotency_key=idempotency_key,
            first_processed_at=first_processed_at,
            outcome=outcome,
        )
        by_event = self._session.scalar(
            select(ProcessedMessageRow).where(
                ProcessedMessageRow.company_id == str(message.company_id),
                ProcessedMessageRow.consumer_name == message.consumer_name,
                ProcessedMessageRow.event_id == str(message.event_id),
                ProcessedMessageRow.event_version == message.event_version,
            )
        )
        by_idempotency = self._session.scalar(
            select(ProcessedMessageRow).where(
                ProcessedMessageRow.company_id == str(message.company_id),
                ProcessedMessageRow.consumer_name == message.consumer_name,
                ProcessedMessageRow.idempotency_key == message.idempotency_key,
            )
        )
        existing = by_event or by_idempotency
        if existing is not None:
            stored = _processed_message(existing)
            if (
                stored.outcome_digest != message.outcome_digest
                or stored.event_id != message.event_id
                or stored.event_version != message.event_version
                or stored.idempotency_key != message.idempotency_key
            ):
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return stored

        row = ProcessedMessageRow(
            company_id=str(message.company_id),
            consumer_name=message.consumer_name,
            event_id=str(message.event_id),
            event_version=message.event_version,
            idempotency_key=message.idempotency_key,
            first_processed_at=message.first_processed_at,
            outcome_digest=message.outcome_digest,
        )
        self._session.add(row)
        self._session.flush()
        return _processed_message(row)

    def find(
        self,
        context: TenantContext,
        *,
        consumer_name: str,
        event_id: str | OpaqueId,
        event_version: int,
        idempotency_key: str,
    ) -> ProcessedMessage | None:
        checked = require_tenant_context(context)
        checked_event_id = OpaqueId(event_id)
        by_event = self._session.scalar(
            select(ProcessedMessageRow).where(
                ProcessedMessageRow.company_id == str(checked.company_id),
                ProcessedMessageRow.consumer_name == consumer_name,
                ProcessedMessageRow.event_id == str(checked_event_id),
                ProcessedMessageRow.event_version == event_version,
            )
        )
        by_idempotency = self._session.scalar(
            select(ProcessedMessageRow).where(
                ProcessedMessageRow.company_id == str(checked.company_id),
                ProcessedMessageRow.consumer_name == consumer_name,
                ProcessedMessageRow.idempotency_key == idempotency_key,
            )
        )
        existing = by_event or by_idempotency
        if existing is None:
            return None
        message = _processed_message(existing)
        if (
            message.event_id != checked_event_id
            or message.event_version != event_version
            or message.idempotency_key != idempotency_key
        ):
            raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
        return message


class SQLAlchemyAuditEventStore:
    def __init__(
        self,
        session: Session,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._session = session
        self._clock = clock
        self._id_generator = id_generator

    def append(self, context: TenantContext, command: AuditAppend) -> AuditEvent:
        checked = ensure_company_scope(context, context.company_id)
        digest = _audit_command_digest(command)
        existing = self._session.scalar(
            select(AuditEventRow).where(
                AuditEventRow.company_id == str(checked.company_id),
                AuditEventRow.idempotency_key == command.idempotency_key,
            )
        )
        if existing is not None:
            if existing.command_digest != digest:
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return _audit_event(existing)

        event = AuditEvent(
            audit_event_id=self._id_generator.new(),
            company_id=checked.company_id,
            actor_type=checked.actor_type,
            actor_id=checked.actor_id,
            action=command.action,
            resource_type=command.resource_type,
            resource_id=command.resource_id,
            result=command.result,
            occurred_at=self._clock.now(),
            request_id=checked.request_id,
            trace_id=checked.trace_id,
            metadata=command.metadata,
            idempotency_key=command.idempotency_key,
        )
        row = AuditEventRow(
            company_id=str(event.company_id),
            audit_event_id=str(event.audit_event_id),
            actor_type=event.actor_type.value,
            actor_id=str(event.actor_id),
            action=event.action,
            resource_type=event.resource_type,
            resource_id=str(event.resource_id),
            result=event.result.value,
            occurred_at=event.occurred_at,
            request_id=str(event.request_id),
            trace_id=event.trace_id,
            metadata_payload=plain_operational_payload(event.metadata),
            idempotency_key=event.idempotency_key,
            command_digest=digest,
        )
        self._session.add(row)
        self._session.flush()
        return _audit_event(row)

    def get(self, context: TenantContext, audit_event_id: str | OpaqueId) -> AuditEvent:
        checked = require_tenant_context(context)
        checked_id = OpaqueId(audit_event_id)
        row = self._session.scalar(
            select(AuditEventRow).where(
                AuditEventRow.company_id == str(checked.company_id),
                AuditEventRow.audit_event_id == str(checked_id),
            )
        )
        if row is not None:
            return _audit_event(row)
        cross_tenant = self._session.scalar(
            select(AuditEventRow.audit_event_id).where(
                AuditEventRow.audit_event_id == str(checked_id)
            )
        )
        if cross_tenant is not None:
            raise TenantScopeViolation
        raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)

    def list_for_tenant(self, context: TenantContext) -> tuple[AuditEvent, ...]:
        checked = require_tenant_context(context)
        rows = self._session.scalars(
            select(AuditEventRow)
            .where(AuditEventRow.company_id == str(checked.company_id))
            .order_by(AuditEventRow.occurred_at, AuditEventRow.audit_event_id)
        ).all()
        return tuple(_audit_event(row) for row in rows)


class SQLAlchemyUnitOfWork:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._id_generator = id_generator
        self._session: Session | None = None
        self._committed = False
        self.outbox: SQLAlchemyOutbox
        self.processed_messages: SQLAlchemyProcessedMessageStore
        self.audit_events: SQLAlchemyAuditEventStore

    def __enter__(self) -> SQLAlchemyUnitOfWork:
        if self._session is not None:
            raise RuntimeError("unit of work is already active")
        self._session = self._session_factory()
        self._committed = False
        self.outbox = SQLAlchemyOutbox(self._session)
        self.processed_messages = SQLAlchemyProcessedMessageStore(self._session)
        self.audit_events = SQLAlchemyAuditEventStore(
            self._session,
            clock=self._clock,
            id_generator=self._id_generator,
        )
        return self

    def commit(self) -> None:
        session = self._required_session()
        session.commit()
        self._committed = True

    def rollback(self) -> None:
        session = self._required_session()
        session.rollback()
        self._committed = False

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        session = self._required_session()
        try:
            if exc_type is not None or not self._committed:
                session.rollback()
        finally:
            session.close()
            self._session = None

    def _required_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        return self._session


class SQLAlchemyAuditAppender:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._id_generator = id_generator

    async def append(self, context: TenantContext, command: AuditAppend) -> AuditEvent:
        with self._session_factory.begin() as session:
            store = SQLAlchemyAuditEventStore(
                session,
                clock=self._clock,
                id_generator=self._id_generator,
            )
            return store.append(context, command)

    async def get(
        self,
        context: TenantContext,
        audit_event_id: str | OpaqueId,
    ) -> AuditEvent:
        with self._session_factory() as session:
            store = SQLAlchemyAuditEventStore(
                session,
                clock=self._clock,
                id_generator=self._id_generator,
            )
            return store.get(context, audit_event_id)

    async def list_for_tenant(self, context: TenantContext) -> tuple[AuditEvent, ...]:
        with self._session_factory() as session:
            store = SQLAlchemyAuditEventStore(
                session,
                clock=self._clock,
                id_generator=self._id_generator,
            )
            return store.list_for_tenant(context)


def _outbox_event(row: OutboxEventRow) -> OutboxEvent:
    return OutboxEvent(
        event_id=OpaqueId(row.event_id),
        company_id=OpaqueId(row.company_id),
        event_type=row.event_type,
        event_version=row.event_version,
        aggregate=AggregateRef(
            aggregate_type=row.aggregate_type,
            aggregate_id=OpaqueId(row.aggregate_id),
            version=row.aggregate_version,
        ),
        idempotency_key=row.idempotency_key,
        occurred_at=_utc(row.occurred_at),
        trace_id=row.trace_id,
        correlation_id=OpaqueId(row.correlation_id),
        causation_id=OpaqueId(row.causation_id) if row.causation_id is not None else None,
        payload=cast(Mapping[str, FrozenValue], row.payload),
        status=OutboxStatus(row.status),
        attempt_count=row.attempt_count,
        last_failure_code=row.last_failure_code,
        published_at=_utc(row.published_at) if row.published_at is not None else None,
    )


def _processed_message(row: ProcessedMessageRow) -> ProcessedMessage:
    return ProcessedMessage(
        company_id=OpaqueId(row.company_id),
        consumer_name=row.consumer_name,
        event_id=OpaqueId(row.event_id),
        event_version=row.event_version,
        idempotency_key=row.idempotency_key,
        first_processed_at=_utc(row.first_processed_at),
        outcome_digest=row.outcome_digest,
    )


def _audit_event(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        audit_event_id=OpaqueId(row.audit_event_id),
        company_id=OpaqueId(row.company_id),
        actor_type=ActorType(row.actor_type),
        actor_id=OpaqueId(row.actor_id),
        action=row.action,
        resource_type=row.resource_type,
        resource_id=OpaqueId(row.resource_id),
        result=AuditResult(row.result),
        occurred_at=_utc(row.occurred_at),
        request_id=OpaqueId(row.request_id),
        trace_id=row.trace_id,
        metadata=cast(Mapping[str, FrozenValue], row.metadata_payload),
        idempotency_key=row.idempotency_key,
    )


def _outbox_identity(event: OutboxEvent) -> tuple[object, ...]:
    return (
        event.event_id,
        event.company_id,
        event.event_type,
        event.event_version,
        event.aggregate,
        event.idempotency_key,
        event.occurred_at,
        event.trace_id,
        event.correlation_id,
        event.causation_id,
        plain_operational_payload(event.payload),
    )


def _apply_outbox_state(row: OutboxEventRow, event: OutboxEvent) -> None:
    row.status = event.status.value
    row.attempt_count = event.attempt_count
    row.last_failure_code = event.last_failure_code
    row.published_at = event.published_at


def _audit_command_digest(command: AuditAppend) -> str:
    canonical = json.dumps(
        {
            "action": command.action,
            "resource_type": command.resource_type,
            "resource_id": str(command.resource_id),
            "result": command.result.value,
            "metadata": plain_operational_payload(command.metadata),
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
