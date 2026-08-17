"""Recording upload authorization, digest verification, and resume sequencing."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from threading import Lock

from interview_evidence.interview_engine.domain.turn import RecordingChunk, UploadStatus
from interview_evidence.shared.aws_clients.ports import ProtectedBytes
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(frozen=True, slots=True, repr=False)
class RecordingUploadIntent:
    recording_chunk_id: OpaqueId
    chunk_sequence: int
    upload_url: str
    expires_at: datetime
    required_headers: dict[str, str]

    def __repr__(self) -> str:
        return (
            "RecordingUploadIntent(upload_url=[REDACTED], "
            f"recording_chunk_id={self.recording_chunk_id!r}, "
            f"chunk_sequence={self.chunk_sequence!r}, expires_at={self.expires_at!r}, "
            f"required_header_names={tuple(self.required_headers)!r})"
        )


class RecordingService:
    __slots__ = ("_chunks", "_clock", "_id_generator", "_lock", "_url_ttl")

    def __init__(
        self,
        *,
        clock: Clock | None = None,
        id_generator: UUID7Generator | None = None,
        url_ttl: timedelta = timedelta(minutes=5),
    ) -> None:
        if url_ttl <= timedelta(0):
            raise ValueError("recording upload URL TTL must be positive")
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UUID7Generator(self._clock)
        self._url_ttl = url_ttl
        self._lock = Lock()
        self._chunks: dict[tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], list[RecordingChunk]] = {}

    def authorize(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        sequence: int,
        byte_size: int,
        sha256: str,
    ) -> RecordingUploadIntent:
        ensure_applicant_scope(context, scope)
        if byte_size < 1:
            raise ValueError("recording byte_size must be positive")
        if len(sha256) != 64 or any(character not in "0123456789abcdef" for character in sha256):
            raise ValueError("recording sha256 is invalid")
        checked_session_id = OpaqueId(session_id)
        expected = self.last_verified_sequence(context, scope, checked_session_id) + 1
        if sequence != expected:
            raise ValueError("recording chunk sequence is not contiguous")
        recording_chunk_id = self._id_generator.new()
        return RecordingUploadIntent(
            recording_chunk_id=recording_chunk_id,
            chunk_sequence=sequence,
            upload_url=(
                "https://media.example.invalid/recording/"
                f"{scope.company_id}/{checked_session_id}/{recording_chunk_id}"
            ),
            expires_at=self._clock.now() + self._url_ttl,
            required_headers={
                "content-length": str(byte_size),
                "x-content-sha256": sha256,
            },
        )

    def accept(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
        *,
        sequence: int,
        content: ProtectedBytes,
        sha256: str,
        start_ms: int,
        end_ms: int,
        idempotency_key: str,
    ) -> RecordingChunk:
        ensure_applicant_scope(context, scope)
        checked_session_id = OpaqueId(session_id)
        key = (*_scope_key(scope), checked_session_id)
        payload = content.reveal()
        actual_digest = hashlib.sha256(payload).hexdigest()
        if actual_digest != sha256:
            raise ValueError("recording chunk digest does not match")
        with self._lock:
            chunks = self._chunks.setdefault(key, [])
            replay = next(
                (chunk for chunk in chunks if chunk.idempotency_key == idempotency_key),
                None,
            )
            if replay is not None:
                if (
                    replay.sequence != sequence
                    or replay.content_hash != sha256
                    or replay.byte_size != len(payload)
                    or replay.session_start_ms != start_ms
                    or replay.session_end_ms != end_ms
                ):
                    raise SafeApplicationError(ErrorCode.IDEMPOTENCY_CONFLICT)
                return replay
            expected_sequence = chunks[-1].sequence + 1 if chunks else 1
            if sequence != expected_sequence:
                raise ValueError("recording chunk sequence is not contiguous")
            if chunks and start_ms < chunks[-1].session_end_ms:
                raise ValueError("recording chunk time range overlaps a verified chunk")
            recording_chunk_id = self._id_generator.new()
            chunk = RecordingChunk(
                recording_chunk_id=recording_chunk_id,
                company_id=scope.company_id,
                interview_session_id=checked_session_id,
                sequence=sequence,
                object_key=(
                    f"recording/{scope.company_id}/{checked_session_id}/{recording_chunk_id}"
                ),
                content_hash=sha256,
                byte_size=len(payload),
                session_start_ms=start_ms,
                session_end_ms=end_ms,
                upload_status=UploadStatus.VERIFIED,
                idempotency_key=idempotency_key,
                created_at=self._clock.now(),
            )
            chunks.append(chunk)
            return chunk

    def last_verified_sequence(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        session_id: str | OpaqueId,
    ) -> int:
        ensure_applicant_scope(context, scope)
        chunks = self._chunks.get((*_scope_key(scope), OpaqueId(session_id)), [])
        return chunks[-1].sequence if chunks else 0

    def chunk_ids(self, context: TenantContext, scope: ApplicantScope) -> tuple[OpaqueId, ...]:
        ensure_applicant_scope(context, scope)
        prefix = _scope_key(scope)
        return tuple(
            chunk.recording_chunk_id
            for key, chunks in self._chunks.items()
            if key[:3] == prefix
            for chunk in chunks
        )

    def delete_chunk(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        chunk_id: str | OpaqueId,
    ) -> bool:
        ensure_applicant_scope(context, scope)
        checked_id = OpaqueId(chunk_id)
        prefix = _scope_key(scope)
        for key, chunks in self._chunks.items():
            if key[:3] != prefix:
                continue
            chunks[:] = [chunk for chunk in chunks if chunk.recording_chunk_id != checked_id]
        return checked_id not in self.chunk_ids(context, scope)


def _scope_key(scope: ApplicantScope) -> tuple[OpaqueId, OpaqueId, OpaqueId]:
    return scope.company_id, scope.applicant_id, scope.invitation_id
