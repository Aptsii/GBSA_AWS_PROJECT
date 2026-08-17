from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from interview_evidence.shared.ids import OpaqueId


class OwnershipClass(StrEnum):
    PRIMARY_OWNED = "primary_owned"
    SHARED = "shared"
    CONTEXT_ONLY = "context_only"
    UNRELATED = "unrelated"


@dataclass(frozen=True, slots=True)
class GitRepositoryAnalysis:
    repository_analysis_id: OpaqueId
    company_id: OpaqueId
    submission_id: OpaqueId
    repository_url: str
    default_branch: str
    pinned_head_sha: str
    candidate_identity_inputs: dict[str, object]
    limits_applied: dict[str, object]
    status: str

    def __post_init__(self) -> None:
        for name in ("repository_analysis_id", "company_id", "submission_id"):
            object.__setattr__(self, name, OpaqueId(getattr(self, name)))


@dataclass(frozen=True, slots=True)
class GitCommitAnalysis:
    parent_sha: str
    commit_sha: str
    author_match_inputs: dict[str, object]
    changed_paths: tuple[str, ...]
    patch: str
    ownership_confidence: float
    ownership_class: OwnershipClass

    def __post_init__(self) -> None:
        if not isinstance(self.ownership_class, OwnershipClass):
            object.__setattr__(self, "ownership_class", OwnershipClass(self.ownership_class))
        if not 0 <= self.ownership_confidence <= 1:
            raise ValueError("ownership confidence must be between zero and one")


@dataclass(frozen=True, slots=True)
class CandidateCodeUnit:
    path: str
    language: str
    symbol: str
    original_line_range: tuple[int, int]
    current_line_range: tuple[int, int]
    candidate_owned_regions: tuple[tuple[int, int], ...]
    related_test_ids: tuple[str, ...]
    dependency_ids: tuple[str, ...] = ()
