"""Deterministic cross-lane module fakes backed by canonical contract examples."""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from typing import Any

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_ROOT = REPOSITORY_ROOT / "packages" / "contracts" / "modules" / "v1"
CATALOG_PATH = MODULE_ROOT / "catalog.json"


class FakeFailureMode(StrEnum):
    NOT_FOUND = "not_found"
    RETRYABLE = "retryable"
    NON_RETRYABLE = "non_retryable"


class DeterministicModuleFakes:
    __slots__ = (
        "_company_id",
        "_failures",
        "_replay_digests",
        "_replay_responses",
        "_responses",
    )

    def __init__(
        self,
        *,
        company_id: str | OpaqueId,
        failures: dict[str, FakeFailureMode | str] | None = None,
    ) -> None:
        self._company_id = OpaqueId(company_id)
        self._responses = _load_responses(self._company_id)
        self._failures = {
            interface: FakeFailureMode(mode) for interface, mode in (failures or {}).items()
        }
        unknown = set(self._failures) - set(self._responses)
        if unknown:
            raise ValueError("failure configuration references an unknown interface")
        self._replay_digests: dict[tuple[str, OpaqueId, str], str] = {}
        self._replay_responses: dict[tuple[str, OpaqueId, str], dict[str, Any]] = {}

    @property
    def interfaces(self) -> frozenset[str]:
        return frozenset(self._responses)

    def __getattr__(self, interface: str) -> Callable[..., dict[str, Any]]:
        if interface not in self._responses:
            raise AttributeError(interface)

        def invoke(context: TenantContext, **arguments: Any) -> dict[str, Any]:
            return self._invoke(interface, context, arguments)

        return invoke

    def __repr__(self) -> str:
        return (
            "DeterministicModuleFakes("
            f"interfaces={len(self._responses)}, failures={len(self._failures)}, "
            f"replays={len(self._replay_responses)})"
        )

    def _invoke(
        self,
        interface: str,
        context: TenantContext,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        checked = ensure_company_scope(context, self._company_id)
        failure = self._failures.get(interface)
        if failure is not None:
            raise SafeApplicationError(_failure_code(failure))

        idempotency_key = arguments.get("idempotency_key")
        if isinstance(idempotency_key, str):
            replay_key = (interface, checked.company_id, idempotency_key)
            digest = _request_digest(arguments)
            existing_digest = self._replay_digests.get(replay_key)
            if existing_digest is not None:
                if existing_digest != digest:
                    raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return deepcopy(self._replay_responses[replay_key])
            response = deepcopy(self._responses[interface])
            self._replay_digests[replay_key] = digest
            self._replay_responses[replay_key] = deepcopy(response)
            return response

        return deepcopy(self._responses[interface])


def _load_responses(company_id: OpaqueId) -> dict[str, dict[str, Any]]:
    catalog: dict[str, Any] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    responses: dict[str, dict[str, Any]] = {}
    for snapshot in catalog["snapshots"]:
        example_path = (CATALOG_PATH.parent / snapshot["example"]).resolve()
        example: dict[str, Any] = json.loads(example_path.read_text(encoding="utf-8"))
        scoped_example = _replace_company_id(example, str(company_id))
        for interface in snapshot["interfaces"]:
            responses[interface] = scoped_example
    return responses


def _replace_company_id(value: Any, company_id: str) -> Any:
    if isinstance(value, dict):
        return {
            key: company_id if key == "company_id" else _replace_company_id(item, company_id)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_company_id(item, company_id) for item in value]
    return value


def _request_digest(arguments: dict[str, Any]) -> str:
    return json.dumps(
        arguments,
        default=str,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _failure_code(mode: FakeFailureMode) -> ErrorCode:
    if mode is FakeFailureMode.NOT_FOUND:
        return ErrorCode.RESOURCE_NOT_FOUND
    if mode is FakeFailureMode.RETRYABLE:
        return ErrorCode.DEPENDENCY_UNAVAILABLE
    return ErrorCode.INTERNAL_ERROR
