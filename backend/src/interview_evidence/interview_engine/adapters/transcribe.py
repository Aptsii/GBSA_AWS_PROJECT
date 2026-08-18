"""Streaming transcription result normalization and confidence handling."""

from __future__ import annotations

from dataclasses import dataclass

from interview_evidence.shared.aws_clients.ports import (
    ProtectedText,
    TranscriptionRequest,
    TranscriptionResult,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


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


class Utf8TextTranscriber:
    __slots__ = ()

    async def transcribe(
        self,
        context: TenantContext,
        request: TranscriptionRequest,
    ) -> TranscriptionResult:
        ensure_company_scope(context, request.company_id)
        try:
            text = request.audio.reveal().decode("utf-8").strip()
        except UnicodeDecodeError:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None
        if not text:
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        return TranscriptionResult(
            text=ProtectedText(text),
            confidence=1.0,
            review_required=False,
        )
