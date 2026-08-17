from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.ids import OpaqueId

_HASH = re.compile(r"^[a-f0-9]{64}$")


class TimelineSpeaker(StrEnum):
    INTERVIEWER = "interviewer"
    APPLICANT = "applicant"


class AssetType(StrEnum):
    RAW_CHUNK_SET = "raw_chunk_set"
    FINAL_VIDEO = "final_video"
    AUDIO = "audio"
    VTT = "vtt"
    MANIFEST = "manifest"


class AssetStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    transcript_segment_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    turn_id: OpaqueId
    speaker: TimelineSpeaker
    text: ProtectedText | str
    confidence: float
    session_start_ms: int
    session_end_ms: int
    source_audio_key: str
    version: int
    created_at: datetime
    corrected_by: OpaqueId | None = None

    def __post_init__(self) -> None:
        for field in ("transcript_segment_id", "company_id", "interview_session_id", "turn_id"):
            object.__setattr__(self, field, OpaqueId(getattr(self, field)))
        if self.corrected_by is not None:
            object.__setattr__(self, "corrected_by", OpaqueId(self.corrected_by))
        if not isinstance(self.speaker, TimelineSpeaker):
            object.__setattr__(self, "speaker", TimelineSpeaker(self.speaker))
        if isinstance(self.text, str):
            object.__setattr__(self, "text", ProtectedText(self.text))
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be bounded")
        if self.session_start_ms < 0 or self.session_end_ms <= self.session_start_ms:
            raise ValueError("transcript range is invalid")
        if self.version < 1 or not self.source_audio_key:
            raise ValueError("transcript provenance is invalid")
        object.__setattr__(self, "created_at", _utc(self.created_at))

    @property
    def review_required(self) -> bool:
        return self.confidence < 0.7

    def reveal_text(self) -> str:
        assert isinstance(self.text, ProtectedText)
        return self.text.reveal()


@dataclass(frozen=True, slots=True)
class RecordingAsset:
    recording_asset_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    asset_type: AssetType
    object_key: str
    content_hash: str
    duration_ms: int
    status: AssetStatus
    missing_ranges: tuple[tuple[int, int], ...]
    created_at: datetime

    def __post_init__(self) -> None:
        for field in ("recording_asset_id", "company_id", "interview_session_id"):
            object.__setattr__(self, field, OpaqueId(getattr(self, field)))
        if not isinstance(self.asset_type, AssetType):
            object.__setattr__(self, "asset_type", AssetType(self.asset_type))
        if not isinstance(self.status, AssetStatus):
            object.__setattr__(self, "status", AssetStatus(self.status))
        if not self.object_key or not _HASH.fullmatch(self.content_hash) or self.duration_ms < 1:
            raise ValueError("recording asset integrity is invalid")
        for start, end in self.missing_ranges:
            if start < 0 or end <= start or end > self.duration_ms:
                raise ValueError("missing media range is invalid")
        object.__setattr__(self, "created_at", _utc(self.created_at))

    def available(self, start_ms: int, end_ms: int) -> bool:
        return 0 <= start_ms < end_ms <= self.duration_ms and not any(
            start_ms < missing_end and end_ms > missing_start
            for missing_start, missing_end in self.missing_ranges
        )


@dataclass(frozen=True, slots=True)
class SessionEvent:
    session_event_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    event_type: str
    session_start_ms: int
    session_end_ms: int
    technical_failure: bool
    details: dict[str, object]
    created_at: datetime

    def __post_init__(self) -> None:
        for field in ("session_event_id", "company_id", "interview_session_id"):
            object.__setattr__(self, field, OpaqueId(getattr(self, field)))
        if self.session_start_ms < 0 or self.session_end_ms < self.session_start_ms:
            raise ValueError("session event range is invalid")
        object.__setattr__(self, "created_at", _utc(self.created_at))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)
