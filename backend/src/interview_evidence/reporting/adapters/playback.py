from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


@dataclass(frozen=True, slots=True, repr=False)
class PlaybackReference:
    url: str
    expires_at: datetime


class PlaybackLocator:
    def issue(
        self,
        context: TenantContext,
        *,
        company_id: str | OpaqueId,
        recording_asset_id: str | OpaqueId,
    ) -> PlaybackReference:
        ensure_company_scope(context, company_id)
        asset_id = OpaqueId(recording_asset_id)
        return PlaybackReference(
            f"https://media.example.invalid/playback/{context.company_id}/{asset_id}",
            datetime.now(UTC) + timedelta(minutes=5),
        )
