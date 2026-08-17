"""Speech synthesis, viseme timing, and text-only fallback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


@dataclass(frozen=True, slots=True)
class VisemeMark:
    offset_ms: int
    value: str


@dataclass(frozen=True, slots=True, repr=False)
class SpeechSynthesis:
    text_only: bool
    audio_url: str | None
    audio_expires_at: datetime | None
    speech_marks_url: str | None
    visemes: tuple[VisemeMark, ...]
    degraded_mode: str

    def __repr__(self) -> str:
        return (
            "SpeechSynthesis(audio_url=[REDACTED], speech_marks_url=[REDACTED], "
            f"text_only={self.text_only!r}, audio_expires_at={self.audio_expires_at!r}, "
            f"viseme_count={len(self.visemes)!r}, degraded_mode={self.degraded_mode!r})"
        )


class SpeechSynthesizer:
    __slots__ = ("_clock", "_fail", "_id_generator", "_url_ttl")

    def __init__(
        self,
        *,
        fail: bool = False,
        clock: Clock | None = None,
        id_generator: UUID7Generator | None = None,
        url_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        if url_ttl <= timedelta(0):
            raise ValueError("speech URL TTL must be positive")
        self._fail = fail
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UUID7Generator(self._clock)
        self._url_ttl = url_ttl

    def synthesize(
        self,
        context: TenantContext,
        company_id: str | OpaqueId,
        question: str,
    ) -> SpeechSynthesis:
        checked = ensure_company_scope(context, company_id)
        if not question.strip():
            raise ValueError("question must not be blank")
        if self._fail:
            return SpeechSynthesis(True, None, None, None, (), "text_only")
        audio_id = self._id_generator.new()
        marks_id = self._id_generator.new()
        expires_at = self._clock.now() + self._url_ttl
        base = f"https://media.example.invalid/{checked.company_id}"
        visemes = tuple(
            VisemeMark(offset_ms=index * 120, value="syllable")
            for index, character in enumerate(question)
            if not character.isspace()
        )
        return SpeechSynthesis(
            text_only=False,
            audio_url=f"{base}/speech/{audio_id}",
            audio_expires_at=expires_at,
            speech_marks_url=f"{base}/speech-marks/{marks_id}",
            visemes=visemes,
            degraded_mode="none",
        )
