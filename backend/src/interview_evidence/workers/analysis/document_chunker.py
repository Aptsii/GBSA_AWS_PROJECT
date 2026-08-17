from __future__ import annotations

import hashlib
from dataclasses import dataclass

from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.submission_analysis.domain.source import SourceLocation
from interview_evidence.workers.analysis.document_extract import ExtractedDocument


@dataclass(frozen=True, slots=True)
class ExtractedChunk:
    ordinal: int
    text: ProtectedText
    location: SourceLocation
    source_hash: str
    chunk_hash: str


class DocumentChunker:
    __slots__ = ("_max_characters", "_overlap_characters")

    def __init__(self, *, max_characters: int = 1_200, overlap_characters: int = 120) -> None:
        if max_characters < 16 or overlap_characters < 0 or overlap_characters >= max_characters:
            raise ValueError("invalid chunk size configuration")
        self._max_characters = max_characters
        self._overlap_characters = overlap_characters

    def chunk(self, document: ExtractedDocument) -> tuple[ExtractedChunk, ...]:
        chunks: list[ExtractedChunk] = []
        ordinal = 0
        for section in document.sections:
            text = section.text.reveal()
            start = 0
            while start < len(text):
                end = min(len(text), start + self._max_characters)
                if end < len(text):
                    boundary = text.rfind(" ", start, end)
                    if boundary > start:
                        end = boundary
                value = text[start:end].strip()
                if value:
                    chunks.append(
                        ExtractedChunk(
                            ordinal=ordinal,
                            text=ProtectedText(value),
                            location=SourceLocation(
                                page=section.page,
                                section=section.title,
                                start_offset=start,
                            ),
                            source_hash=document.content_hash,
                            chunk_hash=hashlib.sha256(value.encode()).hexdigest(),
                        )
                    )
                    ordinal += 1
                if end == len(text):
                    break
                start = max(start + 1, end - self._overlap_characters)
        return tuple(chunks)
