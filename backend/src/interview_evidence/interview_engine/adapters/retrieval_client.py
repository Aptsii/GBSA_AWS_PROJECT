"""Lane B public-contract consumer with deterministic no-result fallback."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Protocol

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import (
    ApplicantScope,
    TenantContext,
    ensure_applicant_scope,
    require_tenant_context,
)


class RetrievalContracts(Protocol):
    def retrieve_context(
        self, context: TenantContext, **arguments: object
    ) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class RetrievalItem:
    rank: int
    score: float
    source_reference: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    results: tuple[RetrievalItem, ...]
    degraded_mode: Literal["none", "search_fallback"]
    retrieval_config_version: str


class RetrievalClient:
    __slots__ = ("_contracts",)

    def __init__(self, contracts: RetrievalContracts) -> None:
        self._contracts = contracts

    def retrieve(
        self,
        context: TenantContext,
        *,
        query: str,
        scope: ApplicantScope | None = None,
        query_vector: tuple[float, ...] = (),
        criterion_id: str | OpaqueId | None = None,
        interview_session_id: str | OpaqueId | None = None,
        config_version: str = "hybrid-v1",
        limit: int = 10,
    ) -> RetrievalResult:
        require_tenant_context(context)
        if not query.strip():
            raise ValueError("retrieval query must not be blank")
        arguments: dict[str, object] = {"query_text": query}
        if scope is not None:
            ensure_applicant_scope(context, scope)
            if criterion_id is None or interview_session_id is None:
                raise ValueError("scoped retrieval requires criterion and session identifiers")
            arguments.update(
                {
                    "scope": scope,
                    "query_vector": query_vector,
                    "criterion_id": OpaqueId(criterion_id),
                    "interview_session_id": OpaqueId(interview_session_id),
                    "config_version": config_version,
                    "limit": limit,
                }
            )
        try:
            payload = self._contracts.retrieve_context(context, **arguments)
        except SafeApplicationError as error:
            if error.code not in {
                ErrorCode.DEPENDENCY_TIMEOUT,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
            }:
                raise
            return RetrievalResult((), "search_fallback", config_version)
        except TimeoutError:
            return RetrievalResult((), "search_fallback", config_version)

        results = _parse_results(payload.get("results"))
        returned_version = payload.get("retrieval_config_version", config_version)
        if not isinstance(returned_version, str):
            raise ValueError("retrieval contract returned an invalid config version")
        return RetrievalResult(
            results=results,
            degraded_mode="none" if results else "search_fallback",
            retrieval_config_version=returned_version,
        )


def _parse_results(value: object) -> tuple[RetrievalItem, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("retrieval contract results must be a list")
    parsed: list[RetrievalItem] = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("retrieval contract item must be an object")
        rank = item.get("rank")
        score = item.get("score")
        reference = item.get("source_reference")
        if not isinstance(rank, int) or not isinstance(score, (int, float)):
            raise ValueError("retrieval contract rank or score is invalid")
        if not isinstance(reference, dict):
            raise ValueError("retrieval contract source reference is invalid")
        parsed.append(RetrievalItem(rank, float(score), reference))
    return tuple(parsed)
