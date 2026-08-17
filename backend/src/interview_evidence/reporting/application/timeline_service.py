from __future__ import annotations

from dataclasses import dataclass

from interview_evidence.reporting.domain.timeline import RecordingAsset, TranscriptSegment


@dataclass(frozen=True, slots=True)
class TimelineEntry:
    entry_id: str
    text: str
    seek_ms: int
    end_ms: int
    matched: bool
    media_available: bool


class TimelineService:
    def project(
        self,
        segments: tuple[TranscriptSegment, ...],
        asset: RecordingAsset,
        *,
        query: str | None = None,
    ) -> tuple[TimelineEntry, ...]:
        folded = query.casefold() if query else None
        return tuple(
            TimelineEntry(
                str(segment.transcript_segment_id),
                segment.reveal_text(),
                segment.session_start_ms,
                segment.session_end_ms,
                folded in segment.reveal_text().casefold() if folded else False,
                asset.available(segment.session_start_ms, segment.session_end_ms),
            )
            for segment in segments
        )
