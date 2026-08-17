"""Immutable outbox and consumer-idempotency primitives."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from interview_evidence.shared._validation import (
    FrozenValue,
    freeze_operational_payload,
    plain_operational_payload,
    safe_code,
    utc_instant,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope

_EVENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


class OutboxStatus(StrEnum):
    PENDING = "pending"
    RETRYING = "retrying"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class AggregateRef:
    aggregate_type: str
    aggregate_id: OpaqueId
    version: int

    def __post_init__(self) -> None:
        safe_code(self.aggregate_type, field_name="aggregate_type")
        object.__setattr__(self, "aggregate_id", OpaqueId(self.aggregate_id))
        if self.version < 1:
            raise ValueError("aggregate version must be positive")


@dataclass(frozen=True, slots=True)
class OutboxEvent:
    event_id: OpaqueId
    company_id: OpaqueId
    event_type: str
    event_version: int
    aggregate: AggregateRef
    idempotency_key: str
    occurred_at: datetime
    trace_id: str
    correlation_id: OpaqueId
    causation_id: OpaqueId | None
    payload: Mapping[str, FrozenValue]
    status: OutboxStatus = OutboxStatus.PENDING
    attempt_count: int = 0
    last_failure_code: str | None = None
    published_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_id", OpaqueId(self.event_id))
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "correlation_id", OpaqueId(self.correlation_id))
        if self.causation_id is not None:
            object.__setattr__(self, "causation_id", OpaqueId(self.causation_id))
        if not _EVENT_TYPE.fullmatch(self.event_type):
            raise ValueError("event_type must be a namespaced lower-case code")
        if self.event_version < 1:
            raise ValueError("event_version must be positive")
        safe_code(self.idempotency_key, field_name="idempotency_key")
        if not 16 <= len(self.idempotency_key) <= 128:
            raise ValueError("idempotency_key must contain between 16 and 128 characters")
        safe_code(self.trace_id, field_name="trace_id")
        object.__setattr__(self, "occurred_at", utc_instant(self.occurred_at))
        object.__setattr__(
            self,
            "payload",
            freeze_operational_payload(self.payload, label="outbox payload"),
        )
        if not isinstance(self.status, OutboxStatus):
            object.__setattr__(self, "status", OutboxStatus(self.status))
        if self.attempt_count < 0:
            raise ValueError("attempt_count cannot be negative")
        if self.last_failure_code is not None:
            safe_code(self.last_failure_code, field_name="last_failure_code")
        if self.published_at is not None:
            object.__setattr__(
                self,
                "published_at",
                utc_instant(self.published_at, field_name="published_at"),
            )
        if self.status is OutboxStatus.PUBLISHED and self.published_at is None:
            raise ValueError("published events require published_at")
        if self.status is not OutboxStatus.PUBLISHED and self.published_at is not None:
            raise ValueError("unpublished events cannot have published_at")

    def record_attempt(self, failure_code: str) -> OutboxEvent:
        if self.status is OutboxStatus.PUBLISHED:
            return self
        safe_code(failure_code, field_name="failure_code")
        return replace(
            self,
            status=OutboxStatus.RETRYING,
            attempt_count=self.attempt_count + 1,
            last_failure_code=failure_code,
        )

    def mark_published(self, published_at: datetime) -> OutboxEvent:
        if self.status is OutboxStatus.PUBLISHED:
            return self
        return replace(
            self,
            status=OutboxStatus.PUBLISHED,
            published_at=utc_instant(published_at, field_name="published_at"),
            last_failure_code=None,
        )


@dataclass(frozen=True, slots=True)
class ProcessedMessage:
    company_id: OpaqueId
    consumer_name: str
    event_id: OpaqueId
    event_version: int
    idempotency_key: str
    first_processed_at: datetime
    outcome_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "event_id", OpaqueId(self.event_id))
        safe_code(self.consumer_name, field_name="consumer_name")
        safe_code(self.idempotency_key, field_name="idempotency_key")
        if self.event_version < 1:
            raise ValueError("event_version must be positive")
        if not 16 <= len(self.idempotency_key) <= 128:
            raise ValueError("idempotency_key must contain between 16 and 128 characters")
        object.__setattr__(
            self,
            "first_processed_at",
            utc_instant(self.first_processed_at, field_name="first_processed_at"),
        )
        if not re.fullmatch(r"[a-f0-9]{64}", self.outcome_digest):
            raise ValueError("outcome_digest must be a SHA-256 hex digest")

    @classmethod
    def from_outcome(
        cls,
        *,
        company_id: str | OpaqueId,
        consumer_name: str,
        event_id: str | OpaqueId,
        event_version: int,
        idempotency_key: str,
        first_processed_at: datetime,
        outcome: Mapping[str, object],
    ) -> ProcessedMessage:
        frozen_outcome = freeze_operational_payload(outcome, label="processed outcome")
        canonical = json.dumps(
            plain_operational_payload(frozen_outcome),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return cls(
            company_id=OpaqueId(company_id),
            consumer_name=consumer_name,
            event_id=OpaqueId(event_id),
            event_version=event_version,
            idempotency_key=idempotency_key,
            first_processed_at=first_processed_at,
            outcome_digest=hashlib.sha256(canonical).hexdigest(),
        )


class InMemoryOutbox:
    """Deterministic fake preserving event and idempotency uniqueness invariants."""

    __slots__ = ("_by_event", "_by_idempotency")

    def __init__(self) -> None:
        self._by_event: dict[tuple[OpaqueId, OpaqueId], OutboxEvent] = {}
        self._by_idempotency: dict[tuple[OpaqueId, str], OutboxEvent] = {}

    def add(self, context: TenantContext, event: OutboxEvent) -> OutboxEvent:
        ensure_company_scope(context, event.company_id)
        event_key = (event.company_id, event.event_id)
        idempotency_key = (event.company_id, event.idempotency_key)
        by_event = self._by_event.get(event_key)
        by_idempotency = self._by_idempotency.get(idempotency_key)
        if by_event is not None or by_idempotency is not None:
            original = by_event or by_idempotency
            if original != event:
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return original
        self._by_event[event_key] = event
        self._by_idempotency[idempotency_key] = event
        return event

    def pending(self, context: TenantContext) -> tuple[OutboxEvent, ...]:
        company_id = ensure_company_scope(context, context.company_id).company_id
        events = [
            event
            for (event_company_id, _), event in self._by_event.items()
            if event_company_id == company_id and event.status is not OutboxStatus.PUBLISHED
        ]
        events.sort(key=lambda event: (event.occurred_at, str(event.event_id)))
        return tuple(events)

    def __repr__(self) -> str:
        return f"InMemoryOutbox(events={len(self._by_event)})"


class InMemoryProcessedMessageStore:
    """Deterministic fake with consumer/event and consumer/idempotency uniqueness."""

    __slots__ = ("_by_event", "_by_idempotency")

    def __init__(self) -> None:
        self._by_event: dict[tuple[OpaqueId, str, OpaqueId, int], ProcessedMessage] = {}
        self._by_idempotency: dict[tuple[OpaqueId, str, str], ProcessedMessage] = {}

    def record(self, context: TenantContext, message: ProcessedMessage) -> ProcessedMessage:
        ensure_company_scope(context, message.company_id)
        event_key = (
            message.company_id,
            message.consumer_name,
            message.event_id,
            message.event_version,
        )
        idempotency_key = (
            message.company_id,
            message.consumer_name,
            message.idempotency_key,
        )
        by_event = self._by_event.get(event_key)
        by_idempotency = self._by_idempotency.get(idempotency_key)
        if by_event is not None or by_idempotency is not None:
            original = by_event if by_event is not None else by_idempotency
            if original is None:  # Defensive narrowing for static analysis.
                raise SafeApplicationError(ErrorCode.INTERNAL_ERROR)
            if (
                original.outcome_digest != message.outcome_digest
                or original.event_id != message.event_id
                or original.event_version != message.event_version
                or original.idempotency_key != message.idempotency_key
            ):
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return original
        self._by_event[event_key] = message
        self._by_idempotency[idempotency_key] = message
        return message

    def __repr__(self) -> str:
        return f"InMemoryProcessedMessageStore(messages={len(self._by_event)})"
