"""Protected tenant-scoped audit append interface and deterministic fake."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from interview_evidence.shared._validation import (
    FrozenValue,
    freeze_operational_payload,
    plain_operational_payload,
    safe_code,
    utc_instant,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import (
    ActorType,
    TenantContext,
    TenantScopeViolation,
    ensure_company_scope,
)


class AuditResult(StrEnum):
    SUCCESS = "succeeded"
    DENIED = "denied"
    FAILURE = "failed"


@dataclass(frozen=True, slots=True)
class AuditAppend:
    action: str
    resource_type: str
    resource_id: OpaqueId
    result: AuditResult
    metadata: Mapping[str, FrozenValue]
    idempotency_key: str

    def __post_init__(self) -> None:
        safe_code(self.action, field_name="action")
        safe_code(self.resource_type, field_name="resource_type")
        object.__setattr__(self, "resource_id", OpaqueId(self.resource_id))
        if not isinstance(self.result, AuditResult):
            object.__setattr__(self, "result", AuditResult(self.result))
        safe_code(self.idempotency_key, field_name="idempotency_key")
        if not 16 <= len(self.idempotency_key) <= 128:
            raise ValueError("idempotency_key must contain between 16 and 128 characters")
        try:
            protected_metadata = freeze_operational_payload(
                self.metadata,
                label="audit metadata",
            )
        except ValueError as error:
            raise ValueError(
                "audit metadata must contain sanitized codes and opaque IDs only"
            ) from error
        object.__setattr__(self, "metadata", protected_metadata)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    audit_event_id: OpaqueId
    company_id: OpaqueId
    actor_type: ActorType
    actor_id: OpaqueId
    action: str
    resource_type: str
    resource_id: OpaqueId
    result: AuditResult
    occurred_at: datetime
    request_id: OpaqueId
    trace_id: str
    metadata: Mapping[str, FrozenValue]
    idempotency_key: str

    def __post_init__(self) -> None:
        for attribute in (
            "audit_event_id",
            "company_id",
            "actor_id",
            "resource_id",
            "request_id",
        ):
            object.__setattr__(self, attribute, OpaqueId(getattr(self, attribute)))
        if not isinstance(self.actor_type, ActorType):
            object.__setattr__(self, "actor_type", ActorType(self.actor_type))
        if not isinstance(self.result, AuditResult):
            object.__setattr__(self, "result", AuditResult(self.result))
        safe_code(self.action, field_name="action")
        safe_code(self.resource_type, field_name="resource_type")
        safe_code(self.trace_id, field_name="trace_id")
        safe_code(self.idempotency_key, field_name="idempotency_key")
        object.__setattr__(
            self,
            "occurred_at",
            utc_instant(self.occurred_at, field_name="occurred_at"),
        )
        object.__setattr__(
            self,
            "metadata",
            freeze_operational_payload(self.metadata, label="audit metadata"),
        )


@runtime_checkable
class AuditAppender(Protocol):
    async def append(self, context: TenantContext, command: AuditAppend) -> AuditEvent: ...


class InMemoryAuditAppender:
    """Append-only fake that derives security-sensitive fields from TenantContext."""

    __slots__ = ("_by_id", "_by_idempotency", "_clock", "_digests", "_id_generator")

    def __init__(self, *, clock: Clock, id_generator: UUID7Generator) -> None:
        self._clock = clock
        self._id_generator = id_generator
        self._by_id: dict[tuple[OpaqueId, OpaqueId], AuditEvent] = {}
        self._by_idempotency: dict[tuple[OpaqueId, str], AuditEvent] = {}
        self._digests: dict[tuple[OpaqueId, str], str] = {}

    async def append(self, context: TenantContext, command: AuditAppend) -> AuditEvent:
        checked = ensure_company_scope(context, context.company_id)
        idempotency_key = (checked.company_id, command.idempotency_key)
        command_digest = _command_digest(command)
        existing = self._by_idempotency.get(idempotency_key)
        if existing is not None:
            if self._digests[idempotency_key] != command_digest:
                raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
            return existing
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
        self._by_id[(event.company_id, event.audit_event_id)] = event
        self._by_idempotency[idempotency_key] = event
        self._digests[idempotency_key] = command_digest
        return event

    async def get(self, context: TenantContext, audit_event_id: OpaqueId) -> AuditEvent:
        checked_id = OpaqueId(audit_event_id)
        own = self._by_id.get((context.company_id, checked_id))
        if own is not None:
            ensure_company_scope(context, own.company_id)
            return own
        if any(event_id == checked_id for _, event_id in self._by_id):
            raise TenantScopeViolation
        raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)

    async def list_for_tenant(self, context: TenantContext) -> tuple[AuditEvent, ...]:
        company_id = ensure_company_scope(context, context.company_id).company_id
        events = [
            event
            for (event_company_id, _), event in self._by_id.items()
            if event_company_id == company_id
        ]
        events.sort(key=lambda event: (event.occurred_at, str(event.audit_event_id)))
        return tuple(events)

    def __repr__(self) -> str:
        return f"InMemoryAuditAppender(events={len(self._by_id)})"


def _command_digest(command: AuditAppend) -> str:
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
