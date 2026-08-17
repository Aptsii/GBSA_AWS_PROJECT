from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from interview_evidence.reporting.domain.timeline import AssetStatus, AssetType, RecordingAsset
from interview_evidence.shared.ids import OpaqueId, UUID7Generator


class MediaProcessor:
    def __init__(self) -> None:
        self._ids = UUID7Generator()

    def build_manifest(
        self,
        *,
        company_id: str | OpaqueId,
        session_id: str | OpaqueId,
        chunks: tuple[tuple[int, int, bytes], ...],
    ) -> RecordingAsset:
        if not chunks:
            raise ValueError("recording chunks are required")
        ordered = sorted(chunks)
        missing: list[tuple[int, int]] = []
        cursor = 0
        payload = bytearray()
        for start, end, content in ordered:
            if start > cursor:
                missing.append((cursor, start))
            if end <= start:
                raise ValueError("recording range is invalid")
            cursor = max(cursor, end)
            payload.extend(content)
        asset_id = self._ids.new()
        return RecordingAsset(
            asset_id,
            OpaqueId(company_id),
            OpaqueId(session_id),
            AssetType.FINAL_VIDEO,
            f"reporting/{company_id}/{session_id}/{asset_id}",
            hashlib.sha256(payload).hexdigest(),
            cursor,
            AssetStatus.PARTIAL if missing else AssetStatus.READY,
            tuple(missing),
            datetime.now(UTC),
        )
