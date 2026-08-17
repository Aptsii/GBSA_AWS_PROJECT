"""Measure server-side Evidence selection to playback-reference readiness."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import mean
from time import perf_counter

from interview_evidence.reporting.adapters.playback import PlaybackLocator
from interview_evidence.reporting.application.evidence_service import EvidenceService
from interview_evidence.reporting.application.timeline_service import TimelineEntry, TimelineService
from interview_evidence.reporting.domain.report import Evidence
from interview_evidence.reporting.domain.timeline import RecordingAsset, TranscriptSegment
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ActorType, TenantContext

DEFAULT_SEGMENTS = 500
DEFAULT_ITERATIONS = 200
MAXIMUM_READY_SECONDS = 2.0


@dataclass(frozen=True, slots=True)
class SeekFixture:
    context: TenantContext
    evidence: Evidence
    segments: tuple[TranscriptSegment, ...]
    asset: RecordingAsset


@dataclass(frozen=True, slots=True)
class SeekResult:
    entry: TimelineEntry
    playback_url: str


@dataclass(frozen=True, slots=True)
class SeekReport:
    segment_count: int
    iterations: int
    average_seconds: float
    p95_seconds: float
    maximum_seconds: float
    maximum_ready_seconds: float
    seek_offset_error_ms: int
    passed: bool


def _percentile(samples: list[float], percentile: float) -> float:
    if not samples:
        raise ValueError("percentile requires at least one sample")
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * percentile) - 1))
    return ordered[index]


def _build_fixture(segment_count: int) -> SeekFixture:
    if segment_count < 1:
        raise ValueError("segment_count must be positive")

    clock = FixedClock(datetime(2026, 8, 17, 13, 0, tzinfo=UTC))
    id_generator = UUID7Generator(clock)
    company_id = id_generator.new()
    session_id = id_generator.new()
    actor_id = id_generator.new()
    context = TenantContext(
        company_id=company_id,
        actor_type=ActorType.COMPANY_USER,
        actor_id=actor_id,
        request_id=id_generator.new(),
        trace_id="evidence-seek-load",
    )
    segments = tuple(
        TranscriptSegment(
            transcript_segment_id=id_generator.new(),
            company_id=company_id,
            interview_session_id=session_id,
            turn_id=id_generator.new(),
            speaker="applicant",
            text=f"Evidence 탐색 성능 측정을 위한 최종 답변 구간 {index}",
            confidence=0.99,
            session_start_ms=index * 2_000,
            session_end_ms=(index * 2_000) + 1_500,
            source_audio_key=f"audio/{session_id}/{index:06d}",
            version=1,
            created_at=clock.now(),
        )
        for index in range(segment_count)
    )
    selected = segments[-1]
    evidence = Evidence(
        evidence_id=id_generator.new(),
        company_id=company_id,
        report_item_id=id_generator.new(),
        criterion_id=id_generator.new(),
        competency_model_version_id=id_generator.new(),
        answer_turn_id=selected.turn_id,
        transcript_segment_id=selected.transcript_segment_id,
        video_start_ms=selected.session_start_ms,
        video_end_ms=selected.session_end_ms,
        observation="최종 답변에 구체적인 복구 순서가 포함됨",
        rationale="지원자 본인의 최종 답변 구간과 직접 연결됨",
        sufficiency="direct",
        generation_version="evidence-seek-load-v1",
        created_at=clock.now(),
    )
    asset = RecordingAsset(
        recording_asset_id=id_generator.new(),
        company_id=company_id,
        interview_session_id=session_id,
        asset_type="final_video",
        object_key=f"recording/{company_id}/{session_id}/final.mp4",
        content_hash="a" * 64,
        duration_ms=segment_count * 2_000,
        status="ready",
        missing_ranges=(),
        created_at=clock.now(),
    )
    return SeekFixture(context=context, evidence=evidence, segments=segments, asset=asset)


def _seek(fixture: SeekFixture) -> SeekResult:
    EvidenceService().validate_anchor(
        answer_turn_final=True,
        answer_speaker="applicant",
        transcript_within_turn=True,
        media_available=fixture.asset.available(
            fixture.evidence.video_start_ms,
            fixture.evidence.video_end_ms,
        ),
        technical_failure=False,
    )
    timeline = TimelineService().project(fixture.segments, fixture.asset)
    entry = next(
        item
        for item in timeline
        if item.entry_id == str(fixture.evidence.transcript_segment_id)
    )
    if not entry.media_available:
        raise AssertionError("selected Evidence does not have an available media range")
    playback = PlaybackLocator().issue(
        fixture.context,
        company_id=fixture.evidence.company_id,
        recording_asset_id=fixture.asset.recording_asset_id,
    )
    return SeekResult(entry=entry, playback_url=playback.url)


def measure_evidence_seek(
    *,
    segment_count: int = DEFAULT_SEGMENTS,
    iterations: int = DEFAULT_ITERATIONS,
) -> SeekReport:
    if iterations < 1:
        raise ValueError("iterations must be positive")
    fixture = _build_fixture(segment_count)
    _seek(fixture)

    samples: list[float] = []
    last_result: SeekResult | None = None
    for _iteration in range(iterations):
        started_at = perf_counter()
        last_result = _seek(fixture)
        samples.append(perf_counter() - started_at)

    assert last_result is not None
    seek_offset_error_ms = abs(last_result.entry.seek_ms - fixture.evidence.video_start_ms)
    maximum_seconds = max(samples)
    passed = (
        maximum_seconds <= MAXIMUM_READY_SECONDS
        and seek_offset_error_ms <= 2_000
        and bool(last_result.playback_url)
    )
    return SeekReport(
        segment_count=segment_count,
        iterations=iterations,
        average_seconds=mean(samples),
        p95_seconds=_percentile(samples, 0.95),
        maximum_seconds=maximum_seconds,
        maximum_ready_seconds=MAXIMUM_READY_SECONDS,
        seek_offset_error_ms=seek_offset_error_ms,
        passed=passed,
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--segments", type=int, default=DEFAULT_SEGMENTS)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    report = measure_evidence_seek(
        segment_count=arguments.segments,
        iterations=arguments.iterations,
    )
    sys.stdout.write(json.dumps(asdict(report), sort_keys=True, indent=2) + "\n")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
