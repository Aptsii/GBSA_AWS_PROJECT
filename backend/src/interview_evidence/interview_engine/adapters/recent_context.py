"""Tenant-scoped DynamoDB-style recent context hot view."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope

ContextItem = dict[str, object]


class RecentContextView:
    __slots__ = ("_available", "_records")

    def __init__(self) -> None:
        self._available = True
        self._records: dict[
            tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], tuple[ContextItem, ...]
        ] = {}

    def set_available(self, available: bool) -> None:
        self._available = available

    def replace(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        turns: Sequence[Mapping[str, object]],
    ) -> tuple[ContextItem, ...]:
        self._authorize(context, scope)
        items = tuple(dict(turn) for turn in turns)
        self._records[(*_scope_key(scope), OpaqueId(session_id))] = items
        return tuple(dict(item) for item in items)

    def load(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
    ) -> tuple[ContextItem, ...]:
        self._authorize(context, scope)
        items = self._records.get((*_scope_key(scope), OpaqueId(session_id)), ())
        return tuple(dict(item) for item in items)

    def delete(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
    ) -> bool:
        self._authorize(context, scope)
        key = (*_scope_key(scope), OpaqueId(session_id))
        self._records.pop(key, None)
        return key not in self._records

    def session_ids(self, context: TenantContext, scope: ApplicantScope) -> tuple[OpaqueId, ...]:
        self._authorize(context, scope)
        prefix = _scope_key(scope)
        return tuple(key[3] for key in self._records if key[:3] == prefix)

    def _authorize(self, context: TenantContext, scope: ApplicantScope) -> None:
        ensure_applicant_scope(context, scope)
        if not self._available:
            raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE)


def _scope_key(scope: ApplicantScope) -> tuple[OpaqueId, OpaqueId, OpaqueId]:
    return scope.company_id, scope.applicant_id, scope.invitation_id
