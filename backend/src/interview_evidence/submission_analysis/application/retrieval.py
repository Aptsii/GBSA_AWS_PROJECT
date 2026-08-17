from __future__ import annotations

import math
import re
from dataclasses import dataclass

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope
from interview_evidence.submission_analysis.adapters.search import InMemorySubmissionSearch
from interview_evidence.submission_analysis.domain.source import SourceReference

_TOKEN = re.compile(r"[A-Za-z0-9_가-힣]+")


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    scope: ApplicantScope
    query_text: str
    query_vector: tuple[float, ...]
    criterion_id: OpaqueId
    interview_session_id: OpaqueId
    config_version: str
    exact_symbol: str | None = None
    limit: int = 10

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_id", OpaqueId(self.criterion_id))
        object.__setattr__(self, "interview_session_id", OpaqueId(self.interview_session_id))
        if not 1 <= self.limit <= 100:
            raise ValueError("retrieval limit must be between one and one hundred")


@dataclass(frozen=True, slots=True)
class RetrievedResult:
    rank: int
    score: float
    source_reference: SourceReference


@dataclass(frozen=True, slots=True)
class RetrievedContext:
    company_id: OpaqueId
    applicant_id: OpaqueId
    interview_session_id: OpaqueId
    criterion_id: OpaqueId
    retrieval_config_version: str
    results: tuple[RetrievedResult, ...]


class HybridRetriever:
    __slots__ = ("_exact_symbol_boost", "_index", "_lexical_weight", "_vector_weight")

    def __init__(
        self,
        index: InMemorySubmissionSearch,
        *,
        vector_weight: float = 0.6,
        lexical_weight: float = 0.4,
        exact_symbol_boost: float = 0.25,
    ) -> None:
        if min(vector_weight, lexical_weight, exact_symbol_boost) < 0:
            raise ValueError("retrieval weights cannot be negative")
        self._index = index
        self._vector_weight = vector_weight
        self._lexical_weight = lexical_weight
        self._exact_symbol_boost = exact_symbol_boost

    def retrieve(self, context: TenantContext, query: RetrievalQuery) -> RetrievedContext:
        ensure_applicant_scope(context, query.scope)
        query_tokens = self._tokens(query.query_text)
        scored: list[tuple[float, SourceReference]] = []
        for record in self._index.candidates(context, query.scope):
            vector_score = self._cosine(query.query_vector, record.vector)
            record_tokens = self._tokens(record.text)
            lexical_score = (
                len(query_tokens & record_tokens) / len(query_tokens | record_tokens)
                if query_tokens and record_tokens
                else 0.0
            )
            symbol_boost = (
                self._exact_symbol_boost
                if query.exact_symbol is not None and query.exact_symbol in record.symbols
                else 0.0
            )
            score = max(
                0.0,
                self._vector_weight * vector_score
                + self._lexical_weight * lexical_score
                + symbol_boost,
            )
            if score > 0:
                scored.append((score, record.reference))
        scored.sort(key=lambda item: (-item[0], str(item[1].source_id)))
        results = tuple(
            RetrievedResult(rank=index + 1, score=round(score, 6), source_reference=reference)
            for index, (score, reference) in enumerate(scored[: query.limit])
        )
        return RetrievedContext(
            company_id=query.scope.company_id,
            applicant_id=query.scope.applicant_id,
            interview_session_id=query.interview_session_id,
            criterion_id=query.criterion_id,
            retrieval_config_version=query.config_version,
            results=results,
        )

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token.casefold() for token in _TOKEN.findall(value)}

    @staticmethod
    def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
        if len(left) != len(right):
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return max(
            0.0, sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
        )
