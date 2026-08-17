from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.ids import OpaqueId

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class SourceLocation:
    page: int | None = None
    section: str | None = None
    path: str | None = None
    symbol: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    start_line: int | None = None
    end_line: int | None = None

    def __post_init__(self) -> None:
        for value in (
            self.page,
            self.start_offset,
            self.end_offset,
            self.start_line,
            self.end_line,
        ):
            if value is not None and value < 0:
                raise ValueError("source locations cannot contain negative positions")
        if self.page == 0:
            raise ValueError("page numbers are one-based")

    def as_dict(self) -> dict[str, object]:
        return {
            key: value
            for key, value in {
                "page": self.page,
                "section": self.section,
                "path": self.path,
                "symbol": self.symbol,
                "start_offset": self.start_offset,
                "end_offset": self.end_offset,
                "start_line": self.start_line,
                "end_line": self.end_line,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class SubmissionChunk:
    chunk_id: OpaqueId
    company_id: OpaqueId
    submission_id: OpaqueId
    analysis_id: OpaqueId
    location: SourceLocation
    text: ProtectedText = field(repr=False)
    source_hash: str
    chunk_hash: str
    embedding_model: str
    embedding_version: str
    index_document_id: OpaqueId

    def __post_init__(self) -> None:
        for name in ("chunk_id", "company_id", "submission_id", "analysis_id", "index_document_id"):
            object.__setattr__(self, name, OpaqueId(getattr(self, name)))
        if not _SHA256.fullmatch(self.source_hash) or not _SHA256.fullmatch(self.chunk_hash):
            raise ValueError("source and chunk hashes must be SHA-256 digests")


@dataclass(frozen=True, slots=True)
class SourceReference:
    company_id: OpaqueId
    source_type: Literal["submission_chunk", "candidate_code_unit"]
    source_id: OpaqueId
    source_version: int
    source_location: SourceLocation
    source_hash: str
    ownership_confidence: float | None = None
    evidence_eligible: Literal[False] = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "source_id", OpaqueId(self.source_id))
        if self.source_version < 1:
            raise ValueError("source version must be positive")
        if not _SHA256.fullmatch(self.source_hash):
            raise ValueError("source hash must be a SHA-256 digest")
        if self.ownership_confidence is not None and not 0 <= self.ownership_confidence <= 1:
            raise ValueError("ownership confidence must be between zero and one")

    def snapshot(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "source_type": self.source_type,
            "source_id": str(self.source_id),
            "source_version": self.source_version,
            "source_location": self.source_location.as_dict(),
            "ownership_confidence": self.ownership_confidence,
            "source_hash": self.source_hash,
            "evidence_eligible": False,
        }
