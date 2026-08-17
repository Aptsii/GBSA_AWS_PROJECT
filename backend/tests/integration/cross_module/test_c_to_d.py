from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from interview_evidence.interview_engine.adapters.retrieval_client import RetrievalClient
from interview_evidence.interview_engine.application.interview_service import InterviewService
from interview_evidence.interview_engine.application.recording_service import RecordingService
from interview_evidence.reporting.application.evidence_service import EvidenceService
from interview_evidence.reporting.application.timeline_service import TimelineService
from interview_evidence.reporting.application.transcript_service import TranscriptService
from interview_evidence.reporting.domain.report import AssessmentState, Evidence, ReportItem
from interview_evidence.reporting.domain.timeline import (
    AssetStatus,
    AssetType,
    RecordingAsset,
)
from interview_evidence.shared.aws_clients.ports import ProtectedBytes
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ActorType, ApplicantScope, TenantContext

NOW = datetime(2026, 8, 17, 11, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000301")
APPLICANT_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000302")
INVITATION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000303")
STRATEGY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000304")
MODEL_VERSION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000305")
CRITERION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000306")


class _NoRetrievedSources:
    def retrieve_context(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {"retrieval_config_version": "hybrid-v1", "results": []}


def test_lane_c_final_turn_and_media_become_lane_d_evidence() -> None:
    clock = FixedClock(NOW)
    ids = UUID7Generator(clock)
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    context = TenantContext(
        company_id=COMPANY_ID,
        actor_type=ActorType.APPLICANT,
        actor_id=APPLICANT_ID,
        request_id=ids.new(),
        trace_id="integration-c-to-d",
    )
    interview = InterviewService(
        retrieval=RetrievalClient(_NoRetrievedSources()),
        clock=clock,
        id_generator=ids,
    )
    created = interview.create_session(
        context,
        scope,
        interview_strategy_id=STRATEGY_ID,
        competency_model_version_id=MODEL_VERSION_ID,
        idempotency_key="c-to-d-session-0001",
    )
    started = interview.start(
        context,
        scope,
        created.session.interview_session_id,
        expected_sequence=0,
    )
    finalized = interview.finalize_answer(
        context,
        scope,
        created.session.interview_session_id,
        expected_sequence=started.session_sequence,
        answer_turn_id=ids.new(),
        transcript_text="장애 복구 순서와 데이터 일관성 트레이드오프를 설명했습니다.",
        transcript_confidence=0.94,
        criterion_id=CRITERION_ID,
        criterion_name="문제 해결",
        remaining_criteria=({"criterion_id": CRITERION_ID, "name": "문제 해결"},),
        idempotency_key="c-to-d-answer-0001",
        last_recording_chunk_sequence=1,
    )
    media = b"verified-audio-range"
    media_hash = hashlib.sha256(media).hexdigest()
    chunk = RecordingService(clock=clock, id_generator=ids).accept(
        context,
        scope,
        created.session.interview_session_id,
        sequence=1,
        content=ProtectedBytes(media),
        sha256=media_hash,
        start_ms=1_000,
        end_ms=4_000,
        idempotency_key="c-to-d-recording-0001",
    )

    answer = finalized.answer_turn
    assert answer.text is not None
    segment = TranscriptService().ingest(
        context,
        company_id=answer.company_id,
        interview_session_id=answer.interview_session_id,
        turn_id=answer.turn_id,
        speaker=answer.speaker.value,
        final_turn=answer.evidence_eligible,
        text=answer.text.reveal(),
        confidence=0.94,
        start_ms=chunk.session_start_ms,
        end_ms=chunk.session_end_ms,
        source_audio_key=chunk.object_key,
    )
    asset = RecordingAsset(
        recording_asset_id=ids.new(),
        company_id=COMPANY_ID,
        interview_session_id=created.session.interview_session_id,
        asset_type=AssetType.RAW_CHUNK_SET,
        object_key=chunk.object_key,
        content_hash=chunk.content_hash,
        duration_ms=chunk.session_end_ms,
        status=AssetStatus.READY,
        missing_ranges=(),
        created_at=NOW,
    )
    timeline = TimelineService().project((segment,), asset, query="트레이드오프")
    report_item_id = ids.new()
    item = ReportItem(
        report_item_id=report_item_id,
        report_id=ids.new(),
        criterion_id=CRITERION_ID,
        competency_model_version_id=MODEL_VERSION_ID,
        assessment_state=AssessmentState.NEEDS_FOLLOW_UP,
        observation="검토 전 관찰",
        rationale="확정 답변 범위를 검토합니다.",
        uncertainty="낮음",
    )
    evidence = Evidence(
        evidence_id=ids.new(),
        company_id=COMPANY_ID,
        report_item_id=report_item_id,
        criterion_id=CRITERION_ID,
        competency_model_version_id=MODEL_VERSION_ID,
        answer_turn_id=answer.turn_id,
        transcript_segment_id=segment.transcript_segment_id,
        video_start_ms=segment.session_start_ms,
        video_end_ms=segment.session_end_ms,
        observation="복구 순서와 트레이드오프를 설명했습니다.",
        rationale="확정된 지원자 답변과 검증된 미디어 범위가 일치합니다.",
        sufficiency="direct",
        generation_version="report-v1",
        created_at=NOW,
    )
    attached = EvidenceService().attach(
        item,
        evidence,
        answer_turn_final=answer.status.value == "final",
        answer_speaker=answer.speaker.value,
        transcript_within_turn=True,
        media_available=timeline[0].media_available,
        technical_failure=False,
    )

    assert timeline[0].matched is True
    assert timeline[0].seek_ms == chunk.session_start_ms
    assert attached.evidence == (evidence,)
    assert attached.evidence[0].answer_turn_id == answer.turn_id
