from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.reporting.application.timeline_service import TimelineService
from interview_evidence.reporting.domain.timeline import RecordingAsset, TranscriptSegment

from tests.fixtures.shared.factories import COMPANY_ID, SESSION_ID


def test_timeline_aligns_transcript_and_excludes_missing_media_ranges() -> None:
    segment = TranscriptSegment(
        transcript_segment_id="018f2000-0000-7000-8000-000000000253",
        company_id=COMPANY_ID,
        interview_session_id=SESSION_ID,
        turn_id="018f2000-0000-7000-8000-000000000252",
        speaker="applicant",
        text="장애 복구 답변",
        confidence=0.9,
        session_start_ms=1000,
        session_end_ms=3000,
        source_audio_key="audio/session/1",
        version=1,
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )
    asset = RecordingAsset(
        recording_asset_id="018f2000-0000-7000-8000-000000000254",
        company_id=COMPANY_ID,
        interview_session_id=SESSION_ID,
        asset_type="final_video",
        object_key="recording/session/final",
        content_hash="a" * 64,
        duration_ms=5000,
        status="partial",
        missing_ranges=((3500, 4000),),
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )
    timeline = TimelineService().project((segment,), asset, query="복구")
    assert timeline[0].seek_ms == 1000
    assert timeline[0].matched is True
