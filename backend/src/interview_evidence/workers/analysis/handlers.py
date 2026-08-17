from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(frozen=True, slots=True)
class AnalysisJob:
    company_id: OpaqueId
    scope: ApplicantScope
    submission_id: OpaqueId
    analysis_version: int
    source_type: str
    idempotency_key: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "submission_id", OpaqueId(self.submission_id))
        if self.company_id != self.scope.company_id:
            raise ValueError("analysis job company must match applicant scope")
        if self.analysis_version < 1:
            raise ValueError("analysis version must be positive")


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    status: Literal["ready", "partial", "failed"]
    impact_code: str | None = None


class AnalysisJobHandler:
    __slots__ = ("_attempts", "_digests", "_dlq", "_max_attempts", "_results")

    def __init__(self, *, max_attempts: int = 3) -> None:
        if max_attempts < 1:
            raise ValueError("max attempts must be positive")
        self._max_attempts = max_attempts
        self._attempts: dict[tuple[OpaqueId, str], int] = {}
        self._digests: dict[tuple[OpaqueId, str], str] = {}
        self._results: dict[tuple[OpaqueId, str], AnalysisOutcome] = {}
        self._dlq: set[tuple[OpaqueId, str]] = set()

    @property
    def dlq_count(self) -> int:
        return len(self._dlq)

    def attempts_for(self, job: AnalysisJob) -> int:
        return self._attempts.get((job.company_id, job.idempotency_key), 0)

    def handle(
        self,
        context: TenantContext,
        job: AnalysisJob,
        process: Callable[[AnalysisJob], AnalysisOutcome],
    ) -> AnalysisOutcome:
        ensure_applicant_scope(context, job.scope)
        key = (job.company_id, job.idempotency_key)
        digest = self._digest(job)
        existing_digest = self._digests.get(key)
        if existing_digest is not None and existing_digest != digest:
            raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
        if key in self._results:
            return self._results[key]
        self._digests[key] = digest
        self._attempts[key] = self._attempts.get(key, 0) + 1
        try:
            outcome = process(job)
        except SafeApplicationError as error:
            retryable = error.code in {
                ErrorCode.DEPENDENCY_TIMEOUT,
                ErrorCode.DEPENDENCY_UNAVAILABLE,
                ErrorCode.RATE_LIMITED,
            }
            if retryable and self._attempts[key] < self._max_attempts:
                raise
            prefix = "DLQ_" if retryable else ""
            outcome = AnalysisOutcome(status="failed", impact_code=f"{prefix}{error.code.value}")
            if retryable:
                self._dlq.add(key)
        self._results[key] = outcome
        return outcome

    @staticmethod
    def _digest(job: AnalysisJob) -> str:
        payload = json.dumps(
            {
                "submission_id": str(job.submission_id),
                "analysis_version": job.analysis_version,
                "source_type": job.source_type,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(payload).hexdigest()
