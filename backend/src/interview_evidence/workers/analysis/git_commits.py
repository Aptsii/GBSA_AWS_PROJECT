from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from interview_evidence.submission_analysis.domain.git_analysis import (
    GitCommitAnalysis,
    OwnershipClass,
)

_SHA = re.compile(r"^[a-f0-9]{40}$")


@dataclass(frozen=True, slots=True)
class CommitInput:
    commit_sha: str
    parent_sha: str
    author_name: str
    author_email: str
    changed_paths: tuple[str, ...]
    patch: str

    def __post_init__(self) -> None:
        if not _SHA.fullmatch(self.commit_sha) or not _SHA.fullmatch(self.parent_sha):
            raise ValueError("commit identifiers must be full lowercase SHA-1 values")


class CommitAnalyzer:
    __slots__ = ()

    def analyze(
        self,
        commit: CommitInput,
        *,
        candidate_identity_inputs: Mapping[str, object],
    ) -> GitCommitAnalysis:
        emails = self._identity_values(candidate_identity_inputs.get("emails"))
        names = self._identity_values(candidate_identity_inputs.get("names"))
        email_match = commit.author_email.casefold() in emails
        name_match = commit.author_name.casefold() in names
        confidence = min(1.0, (0.75 if email_match else 0.0) + (0.2 if name_match else 0.0))
        if confidence >= 0.8:
            ownership_class = OwnershipClass.PRIMARY_OWNED
        elif confidence >= 0.6:
            ownership_class = OwnershipClass.SHARED
        elif confidence > 0:
            ownership_class = OwnershipClass.CONTEXT_ONLY
        else:
            ownership_class = OwnershipClass.UNRELATED
        return GitCommitAnalysis(
            parent_sha=commit.parent_sha,
            commit_sha=commit.commit_sha,
            author_match_inputs={
                "email_match": email_match,
                "name_match": name_match,
            },
            changed_paths=commit.changed_paths,
            patch=commit.patch,
            ownership_confidence=confidence,
            ownership_class=ownership_class,
        )

    @staticmethod
    def _identity_values(value: object) -> set[str]:
        if not isinstance(value, list | tuple | set | frozenset):
            return set()
        return {str(item).casefold() for item in value}
