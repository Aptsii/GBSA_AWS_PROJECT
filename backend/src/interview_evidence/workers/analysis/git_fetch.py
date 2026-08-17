from __future__ import annotations

import re
from dataclasses import dataclass

from interview_evidence.submission_analysis.application.submission_validator import (
    SubmissionValidator,
)

_SHA = re.compile(r"^[a-f0-9]{40}$")
_EXCLUDED_PARTS = {".git", ".next", "dist", "node_modules", "vendor", "venv"}


@dataclass(frozen=True, slots=True)
class GitFetchLimits:
    max_files: int = 2_000
    max_total_bytes: int = 50 * 1024 * 1024
    max_file_bytes: int = 512 * 1024

    def __post_init__(self) -> None:
        if min(self.max_files, self.max_total_bytes, self.max_file_bytes) < 1:
            raise ValueError("Git fetch limits must be positive")


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    repository_url: str
    pinned_head_sha: str
    files: dict[str, bytes]
    limits_applied: dict[str, int]
    excluded_count: int
    partial: bool


class PublicRepositoryFetcher:
    __slots__ = ("_limits", "_validator")

    def __init__(self, *, limits: GitFetchLimits | None = None) -> None:
        self._limits = limits or GitFetchLimits()
        self._validator = SubmissionValidator()

    def fetch(
        self,
        repository_url: str,
        *,
        head_sha: str,
        files: dict[str, bytes],
    ) -> RepositorySnapshot:
        url = self._validator.validate_public_url(repository_url, git_only=True)
        if not _SHA.fullmatch(head_sha):
            raise ValueError("repository snapshot requires a pinned full commit SHA")
        accepted: dict[str, bytes] = {}
        total_bytes = 0
        excluded = 0
        partial = False
        for path, content in sorted(files.items()):
            parts = set(path.split("/"))
            if parts & _EXCLUDED_PARTS or b"\x00" in content[:1_024]:
                excluded += 1
                continue
            if len(content) > self._limits.max_file_bytes:
                excluded += 1
                partial = True
                continue
            if (
                len(accepted) >= self._limits.max_files
                or total_bytes + len(content) > self._limits.max_total_bytes
            ):
                partial = True
                break
            accepted[path] = content
            total_bytes += len(content)
        return RepositorySnapshot(
            repository_url=url,
            pinned_head_sha=head_sha,
            files=accepted,
            limits_applied={
                "max_files": self._limits.max_files,
                "max_total_bytes": self._limits.max_total_bytes,
                "max_file_bytes": self._limits.max_file_bytes,
            },
            excluded_count=excluded,
            partial=partial,
        )
