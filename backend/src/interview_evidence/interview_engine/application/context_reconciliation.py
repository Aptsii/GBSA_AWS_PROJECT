"""Outbox-style recent-context reconciliation with durable fallback."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from interview_evidence.interview_engine.adapters.recent_context import (
    ContextItem,
    RecentContextView,
)
from interview_evidence.shared.errors import SafeApplicationError
from interview_evidence.shared.ids import OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


class ReconciliationStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ContextReconciliationEvent:
    event_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    status: ReconciliationStatus
    turn_count: int


class ContextReconciler:
    __slots__ = ("_durable", "_events", "_id_generator", "_view")

    def __init__(
        self,
        view: RecentContextView,
        *,
        id_generator: UUID7Generator | None = None,
    ) -> None:
        self._view = view
        self._id_generator = id_generator or UUID7Generator()
        self._durable: dict[
            tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], tuple[ContextItem, ...]
        ] = {}
        self._events: list[ContextReconciliationEvent] = []

    def reconcile(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        durable_turns: Sequence[Mapping[str, object]],
    ) -> ContextReconciliationEvent:
        ensure_applicant_scope(context, scope)
        checked_session_id = OpaqueId(session_id)
        key = (*_scope_key(scope), checked_session_id)
        durable_copy = tuple(dict(turn) for turn in durable_turns)
        self._durable[key] = durable_copy
        status = ReconciliationStatus.PENDING
        try:
            self._view.replace(context, scope, checked_session_id, durable_copy)
            status = ReconciliationStatus.SYNCED
        except SafeApplicationError:
            status = ReconciliationStatus.DEGRADED
        event = ContextReconciliationEvent(
            event_id=self._id_generator.new(),
            company_id=scope.company_id,
            interview_session_id=checked_session_id,
            status=status,
            turn_count=len(durable_copy),
        )
        self._events.append(event)
        return event

    def load(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
    ) -> tuple[ContextItem, ...]:
        ensure_applicant_scope(context, scope)
        checked_session_id = OpaqueId(session_id)
        key = (*_scope_key(scope), checked_session_id)
        try:
            hot_items = self._view.load(context, scope, checked_session_id)
            if hot_items:
                return hot_items
        except SafeApplicationError:
            pass
        return tuple(dict(item) for item in self._durable.get(key, ()))

    def events(
        self, context: TenantContext, scope: ApplicantScope
    ) -> tuple[ContextReconciliationEvent, ...]:
        ensure_applicant_scope(context, scope)
        return tuple(event for event in self._events if event.company_id == scope.company_id)


def _scope_key(scope: ApplicantScope) -> tuple[OpaqueId, OpaqueId, OpaqueId]:
    return scope.company_id, scope.applicant_id, scope.invitation_id
