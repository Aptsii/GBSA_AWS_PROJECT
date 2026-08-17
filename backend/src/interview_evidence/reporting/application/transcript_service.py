from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.reporting.domain.timeline import TimelineSpeaker, TranscriptSegment
from interview_evidence.shared.ids import OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


class TranscriptService:
    def __init__(self) -> None:
        self._ids = UUID7Generator()
        self._history: dict[tuple[OpaqueId, OpaqueId], list[TranscriptSegment]] = {}

    def ingest(
        self,
        context: TenantContext,
        *,
        company_id: str | OpaqueId,
        interview_session_id: str | OpaqueId,
        turn_id: str | OpaqueId,
        speaker: str | TimelineSpeaker,
        final_turn: bool,
        text: str,
        confidence: float,
        start_ms: int,
        end_ms: int,
        source_audio_key: str,
    ) -> TranscriptSegment:
        ensure_company_scope(context, company_id)
        if not final_turn:
            raise ValueError("only final Turns can be ingested")
        segment = TranscriptSegment(
            self._ids.new(),
            OpaqueId(company_id),
            OpaqueId(interview_session_id),
            OpaqueId(turn_id),
            TimelineSpeaker(speaker),
            text,
            confidence,
            start_ms,
            end_ms,
            source_audio_key,
            1,
            datetime.now(UTC),
        )
        self._history[(context.company_id, segment.transcript_segment_id)] = [segment]
        return segment

    def correct(
        self, context: TenantContext, segment_id: str | OpaqueId, *, text: str
    ) -> TranscriptSegment:
        history = self._history[(context.company_id, OpaqueId(segment_id))]
        original = history[-1]
        corrected = TranscriptSegment(
            original.transcript_segment_id,
            original.company_id,
            original.interview_session_id,
            original.turn_id,
            original.speaker,
            text,
            original.confidence,
            original.session_start_ms,
            original.session_end_ms,
            original.source_audio_key,
            original.version + 1,
            datetime.now(UTC),
            context.actor_id,
        )
        history.append(corrected)
        return corrected

    def history(
        self, context: TenantContext, segment_id: str | OpaqueId
    ) -> tuple[TranscriptSegment, ...]:
        return tuple(self._history[(context.company_id, OpaqueId(segment_id))])
