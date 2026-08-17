from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope


class SourceType(StrEnum):
    COVER_LETTER = "cover_letter"
    RESUME = "resume"
    PDF = "pdf"
    PUBLIC_GIT = "public_git"
    PUBLIC_URL = "public_url"


class SubmissionStatus(StrEnum):
    RECEIVED = "received"
    VALIDATING = "validating"
    ANALYZING = "analyzing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"
    DELETED = "deleted"


class AnalysisStatus(StrEnum):
    RUNNING = "running"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


_TRANSITIONS = {
    SubmissionStatus.RECEIVED: {SubmissionStatus.VALIDATING, SubmissionStatus.FAILED},
    SubmissionStatus.VALIDATING: {SubmissionStatus.ANALYZING, SubmissionStatus.FAILED},
    SubmissionStatus.ANALYZING: {
        SubmissionStatus.READY,
        SubmissionStatus.PARTIAL,
        SubmissionStatus.FAILED,
    },
    SubmissionStatus.READY: {SubmissionStatus.DELETED},
    SubmissionStatus.PARTIAL: {SubmissionStatus.ANALYZING, SubmissionStatus.DELETED},
    SubmissionStatus.FAILED: {SubmissionStatus.ANALYZING, SubmissionStatus.DELETED},
    SubmissionStatus.DELETED: set(),
}


@dataclass(frozen=True, slots=True)
class Submission:
    submission_id: OpaqueId
    scope: ApplicantScope
    source_type: SourceType
    source_uri: str
    original_filename: str | None
    content_hash: str | None
    byte_size: int | None
    media_type: str | None
    status: SubmissionStatus
    created_at: datetime
    failure_code: str | None = None
    impact_summary: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "submission_id", OpaqueId(self.submission_id))
        if not isinstance(self.source_type, SourceType):
            object.__setattr__(self, "source_type", SourceType(self.source_type))
        if not isinstance(self.status, SubmissionStatus):
            object.__setattr__(self, "status", SubmissionStatus(self.status))
        if self.byte_size is not None and self.byte_size < 1:
            raise ValueError("submission byte size must be positive")

    def transition(
        self,
        status: SubmissionStatus,
        *,
        failure_code: str | None = None,
        impact_summary: str | None = None,
    ) -> Submission:
        target = SubmissionStatus(status)
        if target not in _TRANSITIONS[self.status]:
            raise ValueError(f"invalid submission transition: {self.status} -> {target}")
        if target in {SubmissionStatus.PARTIAL, SubmissionStatus.FAILED} and not impact_summary:
            raise ValueError("partial and failed submissions require an impact summary")
        return replace(
            self,
            status=target,
            failure_code=failure_code,
            impact_summary=impact_summary,
        )

    def view(self) -> dict[str, object]:
        return {
            "submission_id": str(self.submission_id),
            "source_type": self.source_type.value,
            "status": self.status.value,
            "failure_code": self.failure_code,
            "impact_summary": self.impact_summary,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class SubmissionAnalysis:
    analysis_id: OpaqueId
    company_id: OpaqueId
    submission_id: OpaqueId
    analysis_version: int
    extractor_version: str
    chunk_config_version: str
    claims: tuple[dict[str, object], ...]
    conflicts: tuple[dict[str, object], ...]
    verification_points: tuple[dict[str, object], ...]
    status: AnalysisStatus
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("analysis_id", "company_id", "submission_id"):
            object.__setattr__(self, name, OpaqueId(getattr(self, name)))
        if self.analysis_version < 1:
            raise ValueError("analysis version must be positive")
        if not isinstance(self.status, AnalysisStatus):
            object.__setattr__(self, "status", AnalysisStatus(self.status))
