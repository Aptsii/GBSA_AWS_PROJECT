"""Applicant-scoped command and upload idempotency."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Lock
from typing import cast

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(frozen=True, slots=True)
class _StoredResult:
    fingerprint: str
    result: object


class ScopedIdempotencyStore:
    __slots__ = ("_lock", "_records")

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[tuple[OpaqueId, OpaqueId, OpaqueId, str, str], _StoredResult] = {}

    def execute[ResultT](
        self,
        context: TenantContext,
        scope: ApplicantScope,
        idempotency_key: str,
        payload: Mapping[str, object],
        operation: Callable[[], ResultT],
        *,
        namespace: str = "command",
    ) -> ResultT:
        ensure_applicant_scope(context, scope)
        _validate_key(idempotency_key)
        _validate_namespace(namespace)
        key = (
            scope.company_id,
            scope.applicant_id,
            scope.invitation_id,
            namespace,
            idempotency_key,
        )
        fingerprint = _fingerprint(payload)
        with self._lock:
            existing = self._records.get(key)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return cast(ResultT, existing.result)
            result = operation()
            self._records[key] = _StoredResult(fingerprint, result)
            return result


def _fingerprint(payload: Mapping[str, object]) -> str:
    try:
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    except (TypeError, ValueError) as error:
        raise ValueError("idempotency payload must be JSON serializable") from error
    return hashlib.sha256(encoded).hexdigest()


def _validate_key(value: str) -> None:
    if not 16 <= len(value) <= 128 or any(character.isspace() for character in value):
        raise ValueError("idempotency_key must contain 16-128 non-whitespace characters")


def _validate_namespace(value: str) -> None:
    if not value or len(value) > 64 or any(character.isspace() for character in value):
        raise ValueError("idempotency namespace must be a safe code")
