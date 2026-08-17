"""Interview Turn, checkpoint, and recording chunk invariants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from interview_evidence.shared.aws_clients.ports import ProtectedText
from interview_evidence.shared.ids import OpaqueId

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class TurnSpeaker(StrEnum):
    INTERVIEWER = "interviewer"
    APPLICANT = "applicant"


class TurnStatus(StrEnum):
    PREPARING = "preparing"
    PRESENTED = "presented"
    RECORDING = "recording"
    FINAL = "final"
    FAILED = "failed"


class HotViewSyncStatus(StrEnum):
    PENDING = "pending"
    SYNCED = "synced"
    DEGRADED = "degraded"


class UploadStatus(StrEnum):
    ISSUED = "issued"
    UPLOADED = "uploaded"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Turn:
    turn_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    sequence: int
    speaker: TurnSpeaker
    status: TurnStatus
    idempotency_key: str
    created_at: datetime
    text: ProtectedText | str | None = None
    target_criterion_id: OpaqueId | None = None
    model_config_version: str | None = None
    finalized_at: datetime | None = None

    def __post_init__(self) -> None:
        for attribute in ("turn_id", "company_id", "interview_session_id"):
            object.__setattr__(self, attribute, OpaqueId(getattr(self, attribute)))
        if self.target_criterion_id is not None:
            object.__setattr__(self, "target_criterion_id", OpaqueId(self.target_criterion_id))
        if not isinstance(self.speaker, TurnSpeaker):
            object.__setattr__(self, "speaker", TurnSpeaker(self.speaker))
        if not isinstance(self.status, TurnStatus):
            object.__setattr__(self, "status", TurnStatus(self.status))
        if isinstance(self.text, str):
            object.__setattr__(self, "text", ProtectedText(self.text))
        if self.text is not None and not isinstance(self.text, ProtectedText):
            raise TypeError("turn text must be protected")
        if self.sequence < 1:
            raise ValueError("turn sequence must be positive")
        _validate_idempotency_key(self.idempotency_key)
        object.__setattr__(self, "created_at", _utc(self.created_at))
        if self.finalized_at is not None:
            object.__setattr__(self, "finalized_at", _utc(self.finalized_at))
        if self.status is TurnStatus.FINAL and (self.text is None or self.finalized_at is None):
            raise ValueError("final Turn requires protected text and finalized_at")
        if self.status is not TurnStatus.FINAL and self.finalized_at is not None:
            raise ValueError("only final Turns may have finalized_at")
        if self.speaker is TurnSpeaker.INTERVIEWER:
            if self.target_criterion_id is None:
                raise ValueError("interviewer Turn requires target_criterion_id")
            if not self.model_config_version:
                raise ValueError("interviewer Turn requires model_config_version")

    @property
    def evidence_eligible(self) -> bool:
        return self.speaker is TurnSpeaker.APPLICANT and self.status is TurnStatus.FINAL


@dataclass(frozen=True, slots=True)
class SessionCheckpoint:
    checkpoint_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    session_sequence: int
    last_media_chunk_sequence: int
    hot_view_sync_status: HotViewSyncStatus
    created_at: datetime
    last_final_turn_id: OpaqueId | None = None
    pending_turn_id: OpaqueId | None = None

    def __post_init__(self) -> None:
        for attribute in ("checkpoint_id", "company_id", "interview_session_id"):
            object.__setattr__(self, attribute, OpaqueId(getattr(self, attribute)))
        for attribute in ("last_final_turn_id", "pending_turn_id"):
            value = getattr(self, attribute)
            if value is not None:
                object.__setattr__(self, attribute, OpaqueId(value))
        if not isinstance(self.hot_view_sync_status, HotViewSyncStatus):
            object.__setattr__(
                self,
                "hot_view_sync_status",
                HotViewSyncStatus(self.hot_view_sync_status),
            )
        if self.session_sequence < 0 or self.last_media_chunk_sequence < 0:
            raise ValueError("checkpoint sequences must be nonnegative")
        object.__setattr__(self, "created_at", _utc(self.created_at))


@dataclass(frozen=True, slots=True)
class RecordingChunk:
    recording_chunk_id: OpaqueId
    company_id: OpaqueId
    interview_session_id: OpaqueId
    sequence: int
    object_key: str
    content_hash: str
    byte_size: int
    session_start_ms: int
    session_end_ms: int
    upload_status: UploadStatus
    idempotency_key: str
    created_at: datetime

    def __post_init__(self) -> None:
        for attribute in ("recording_chunk_id", "company_id", "interview_session_id"):
            object.__setattr__(self, attribute, OpaqueId(getattr(self, attribute)))
        if not isinstance(self.upload_status, UploadStatus):
            object.__setattr__(self, "upload_status", UploadStatus(self.upload_status))
        if self.sequence < 0:
            raise ValueError("recording chunk sequence must be nonnegative")
        if not self.object_key or self.object_key.startswith("/"):
            raise ValueError("recording chunk object_key must be relative")
        if not _SHA256.fullmatch(self.content_hash):
            raise ValueError("recording chunk content_hash must be sha256")
        if self.byte_size < 1:
            raise ValueError("recording chunk byte_size must be positive")
        if self.session_start_ms < 0 or self.session_end_ms <= self.session_start_ms:
            raise ValueError("recording chunk time range is invalid")
        _validate_idempotency_key(self.idempotency_key)
        object.__setattr__(self, "created_at", _utc(self.created_at))


def _validate_idempotency_key(value: str) -> None:
    if not 16 <= len(value) <= 128 or any(character.isspace() for character in value):
        raise ValueError("idempotency_key must contain 16-128 non-whitespace characters")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("domain timestamps must be timezone-aware")
    return value.astimezone(UTC)
