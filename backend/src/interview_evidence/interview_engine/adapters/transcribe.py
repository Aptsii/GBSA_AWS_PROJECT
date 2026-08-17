"""Streaming transcription result normalization and confidence handling."""

from __future__ import annotations

from dataclasses import dataclass

from interview_evidence.shared.aws_clients.ports import ProtectedText


@dataclass(frozen=True, slots=True, repr=False)
class StreamingTranscript:
    text: ProtectedText
    confidence: float
    is_final: bool
    evidence_eligible: bool
    review_required: bool

    def __repr__(self) -> str:
        return (
            "StreamingTranscript(text=[REDACTED], "
            f"confidence={self.confidence!r}, is_final={self.is_final!r}, "
            f"evidence_eligible={self.evidence_eligible!r}, "
            f"review_required={self.review_required!r})"
        )


class StreamingTranscriber:
    __slots__ = ("_review_threshold",)

    def __init__(self, *, review_threshold: float = 0.7) -> None:
        if not 0 <= review_threshold <= 1:
            raise ValueError("review_threshold must be between zero and one")
        self._review_threshold = review_threshold

    def result(self, text: str, *, confidence: float, is_final: bool) -> StreamingTranscript:
        if not 0 <= confidence <= 1:
            raise ValueError("transcription confidence must be between zero and one")
        if not text.strip():
            raise ValueError("transcription text must not be blank")
        return StreamingTranscript(
            text=ProtectedText(text),
            confidence=confidence,
            is_final=is_final,
            evidence_eligible=is_final,
            review_required=is_final and confidence < self._review_threshold,
        )
