from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from interview_evidence.reporting.repositories.postgres import (
    EvidenceRow,
    RecordingAssetRow,
    ReportingRepository,
    ReportItemRow,
    ReportRow,
    SessionEventRow,
    TranscriptSegmentRow,
)
from interview_evidence.shared._validation import FrozenValue
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.messaging.outbox import AggregateRef, OutboxEvent
from interview_evidence.shared.persistence import SQLAlchemyOutbox
from interview_evidence.shared.tenant import TenantContext, ensure_company_scope


class CompletedInterviewProvider(Protocol):
    def get_completed_session_snapshot(
        self,
        context: TenantContext,
        *,
        session_id: str | OpaqueId,
    ) -> dict[str, object]: ...


class SQLAlchemyMediaPostprocessHandler:
    __slots__ = ("_clock", "_id_generator", "_interview_public", "_repository", "_session")

    def __init__(
        self,
        session: Session,
        *,
        interview_public: CompletedInterviewProvider,
        clock: Clock | None = None,
        id_generator: UUID7Generator | None = None,
    ) -> None:
        self._session = session
        self._repository = ReportingRepository(session)
        self._interview_public = interview_public
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UUID7Generator(self._clock)

    def handle_event(
        self,
        context: TenantContext,
        event: object,
    ) -> Mapping[str, object]:
        ensure_company_scope(context, context.company_id)
        if _event_type(event) != "media.postprocess_requested":
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        payload = _event_payload(event)
        session_id = _required_id(payload, "interview_session_id")
        existing = self._session.scalar(
            select(RecordingAssetRow).where(
                RecordingAssetRow.company_id == str(context.company_id),
                RecordingAssetRow.interview_session_id == str(session_id),
            )
        )
        if existing is not None:
            return {
                "recording_asset_id": existing.recording_asset_id,
                "status": existing.status,
            }
        snapshot = self._interview_public.get_completed_session_snapshot(
            context,
            session_id=session_id,
        )
        chunks = sorted(
            (
                item
                for item in _mapping_items(snapshot, "recording_chunks")
                if item.get("upload_status") == "verified"
            ),
            key=lambda item: _required_int(item, "sequence"),
        )
        missing_ranges: list[list[int]] = []
        cursor = 0
        for chunk in chunks:
            start_ms = _required_int(chunk, "session_start_ms")
            end_ms = _required_int(chunk, "session_end_ms")
            if start_ms > cursor:
                missing_ranges.append([cursor, start_ms])
            cursor = max(cursor, end_ms)
        duration_ms = max(1, cursor)
        if not chunks:
            missing_ranges = [[0, duration_ms]]
        status = "failed" if not chunks else "partial" if missing_ranges else "ready"
        asset_id = _event_aggregate_id(event)
        digest_payload = [
            {
                "sequence": _required_int(chunk, "sequence"),
                "content_hash": _required_str(chunk, "content_hash"),
                "start_ms": _required_int(chunk, "session_start_ms"),
                "end_ms": _required_int(chunk, "session_end_ms"),
            }
            for chunk in chunks
        ]
        content_hash = hashlib.sha256(
            json.dumps(digest_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        row = RecordingAssetRow(
            recording_asset_id=str(asset_id),
            company_id=str(context.company_id),
            interview_session_id=str(session_id),
            asset_type="final_video",
            object_key=f"sessions/{session_id}/recording/final/1/{asset_id}",
            content_hash=content_hash,
            duration_ms=duration_ms,
            status=status,
            missing_ranges=missing_ranges,
            created_at=self._clock.now(),
        )
        self._repository.add(context, row)
        if (
            self._session.scalar(
                select(SessionEventRow).where(
                    SessionEventRow.company_id == str(context.company_id),
                    SessionEventRow.interview_session_id == str(session_id),
                    SessionEventRow.event_type == "interview.completed",
                )
            )
            is None
        ):
            self._repository.add(
                context,
                SessionEventRow(
                    session_event_id=str(self._id_generator.new()),
                    company_id=str(context.company_id),
                    interview_session_id=str(session_id),
                    event_type="interview.completed",
                    session_start_ms=duration_ms,
                    session_end_ms=duration_ms,
                    technical_failure=False,
                    details={"media_status": status},
                    created_at=self._clock.now(),
                ),
            )
        return {"recording_asset_id": str(asset_id), "status": status}


class SQLAlchemyReportGenerationHandler:
    __slots__ = ("_clock", "_id_generator", "_interview_public", "_repository", "_session")

    def __init__(
        self,
        session: Session,
        *,
        interview_public: CompletedInterviewProvider,
        clock: Clock | None = None,
        id_generator: UUID7Generator | None = None,
    ) -> None:
        self._session = session
        self._repository = ReportingRepository(session)
        self._interview_public = interview_public
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UUID7Generator(self._clock)

    def handle_event(
        self,
        context: TenantContext,
        event: object,
    ) -> Mapping[str, object]:
        ensure_company_scope(context, context.company_id)
        if _event_type(event) != "report.generation_requested":
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        payload = _event_payload(event)
        session_id = _required_id(payload, "interview_session_id")
        report_version = _required_int(payload, "report_version")
        existing = self._session.scalar(
            select(ReportRow).where(
                ReportRow.company_id == str(context.company_id),
                ReportRow.interview_session_id == str(session_id),
                ReportRow.report_version == report_version,
            )
        )
        if existing is not None:
            return self._report_result(context, existing)
        snapshot = self._interview_public.get_completed_session_snapshot(
            context,
            session_id=session_id,
        )
        transcript_by_turn = self._persist_transcripts(context, snapshot)
        asset = self._session.scalar(
            select(RecordingAssetRow).where(
                RecordingAssetRow.company_id == str(context.company_id),
                RecordingAssetRow.interview_session_id == str(session_id),
            )
        )
        report_id = _event_aggregate_id(event)
        model_version_id = _required_id(payload, "competency_model_version_id")
        turns = sorted(
            _mapping_items(snapshot, "turns"),
            key=lambda item: _required_int(item, "sequence"),
        )
        report_items: list[ReportItemRow] = []
        evidence_rows: list[EvidenceRow] = []
        seen_criteria: set[str] = set()
        confirmed_count = 0
        insufficient_count = 0
        for index, question in enumerate(turns):
            if question.get("speaker") != "interviewer":
                continue
            criterion_id = question.get("target_criterion_id")
            if not isinstance(criterion_id, str) or criterion_id in seen_criteria:
                continue
            seen_criteria.add(criterion_id)
            answer = next(
                (
                    item
                    for item in turns[index + 1 :]
                    if item.get("speaker") == "applicant" and item.get("status") == "final"
                ),
                None,
            )
            report_item_id = self._id_generator.new()
            transcript = (
                transcript_by_turn.get(_required_str(answer, "turn_id"))
                if answer is not None
                else None
            )
            evidence_available = (
                answer is not None
                and transcript is not None
                and asset is not None
                and _media_available(
                    asset,
                    transcript.session_start_ms,
                    transcript.session_end_ms,
                )
            )
            assessment_state = "confirmed" if evidence_available else "insufficient_evidence"
            if evidence_available:
                confirmed_count += 1
            else:
                insufficient_count += 1
            report_items.append(
                ReportItemRow(
                    report_item_id=str(report_item_id),
                    company_id=str(context.company_id),
                    report_id=str(report_id),
                    criterion_id=criterion_id,
                    competency_model_version_id=str(model_version_id),
                    assessment_state=assessment_state,
                    observation="최종 지원자 답변에서 해당 평가 기준 관련 설명을 확인했습니다.",
                    rationale=(
                        "검증된 자막과 미디어 구간이 최종 지원자 Turn에 연결됩니다."
                        if evidence_available
                        else "최종 지원자 답변 또는 검증된 미디어 구간이 충분하지 않습니다."
                    ),
                    uncertainty="검증된 Evidence 범위로 제한됩니다.",
                    follow_up_question=(
                        None if evidence_available else "사람 면접에서 구체적 사례를 확인해 주세요."
                    ),
                )
            )
            if evidence_available and answer is not None and transcript is not None:
                evidence_rows.append(
                    EvidenceRow(
                        evidence_id=str(self._id_generator.new()),
                        company_id=str(context.company_id),
                        report_item_id=str(report_item_id),
                        criterion_id=criterion_id,
                        competency_model_version_id=str(model_version_id),
                        answer_turn_id=_required_str(answer, "turn_id"),
                        transcript_segment_id=transcript.transcript_segment_id,
                        video_start_ms=transcript.session_start_ms,
                        video_end_ms=transcript.session_end_ms,
                        observation="최종 답변에서 평가 기준 관련 실행 판단을 설명했습니다.",
                        rationale=(
                            "최종 지원자 Turn, 자막 구간과 사용 가능한 미디어 구간이 일치합니다."
                        ),
                        sufficiency="direct",
                        generation_version="report-generation-v1",
                        created_at=self._clock.now(),
                    )
                )
        status = "ready" if report_items and confirmed_count == len(report_items) else "partial"
        report = ReportRow(
            report_id=str(report_id),
            company_id=str(context.company_id),
            interview_session_id=str(session_id),
            competency_model_version_id=str(model_version_id),
            report_version=report_version,
            kind="ai_original",
            status=status,
            summary=(
                f"확인됨 {confirmed_count}개, 근거 부족 {insufficient_count}개입니다. "
                "최종 채용 결정은 사람 검토자가 기록합니다."
            ),
            model_config_version="report-generation-v1",
            prompt_version="evidence-report-ko-v1",
            created_at=self._clock.now(),
        )
        self._repository.add(context, report)
        for item in report_items:
            self._repository.add(context, item)
        for evidence in evidence_rows:
            self._repository.add(context, evidence)
        return {
            "report_id": str(report_id),
            "report_version": report_version,
            "status": status,
            "confirmed_count": confirmed_count,
            "partially_confirmed_count": 0,
            "insufficient_evidence_count": insufficient_count,
            "needs_follow_up_count": 0,
        }

    def _persist_transcripts(
        self,
        context: TenantContext,
        snapshot: Mapping[str, object],
    ) -> dict[str, TranscriptSegmentRow]:
        session_id = _required_id(snapshot, "interview_session_id")
        turns = sorted(
            _mapping_items(snapshot, "turns"),
            key=lambda item: _required_int(item, "sequence"),
        )
        chunks = sorted(
            (
                item
                for item in _mapping_items(snapshot, "recording_chunks")
                if item.get("upload_status") == "verified"
            ),
            key=lambda item: _required_int(item, "sequence"),
        )
        checkpoint_media = {
            _required_str(item, "last_final_turn_id"): _required_int(
                item, "last_media_chunk_sequence"
            )
            for item in _mapping_items(snapshot, "checkpoints")
            if isinstance(item.get("last_final_turn_id"), str)
        }
        ranges: dict[str, tuple[int, int, str]] = {}
        previous_media_sequence = 0
        synthetic_cursor = 0
        for turn in turns:
            if turn.get("speaker") != "applicant" or turn.get("status") != "final":
                continue
            turn_id = _required_str(turn, "turn_id")
            last_media_sequence = checkpoint_media.get(turn_id, previous_media_sequence)
            answer_chunks = [
                chunk
                for chunk in chunks
                if previous_media_sequence < _required_int(chunk, "sequence") <= last_media_sequence
            ]
            if answer_chunks:
                start_ms = min(_required_int(chunk, "session_start_ms") for chunk in answer_chunks)
                end_ms = max(_required_int(chunk, "session_end_ms") for chunk in answer_chunks)
                source_key = _required_str(answer_chunks[0], "object_key")
                synthetic_cursor = max(synthetic_cursor, end_ms)
            else:
                start_ms = synthetic_cursor
                end_ms = start_ms + 1_000
                source_key = f"text-only/{turn_id}"
                synthetic_cursor = end_ms
            ranges[turn_id] = (start_ms, end_ms, source_key)
            previous_media_sequence = max(previous_media_sequence, last_media_sequence)
        rows_by_turn: dict[str, TranscriptSegmentRow] = {}
        for index, turn in enumerate(turns):
            text = turn.get("text")
            if not isinstance(text, str):
                continue
            turn_id = _required_str(turn, "turn_id")
            existing = self._session.scalar(
                select(TranscriptSegmentRow).where(
                    TranscriptSegmentRow.company_id == str(context.company_id),
                    TranscriptSegmentRow.interview_session_id == str(session_id),
                    TranscriptSegmentRow.turn_id == turn_id,
                    TranscriptSegmentRow.version == 1,
                )
            )
            if existing is not None:
                rows_by_turn[turn_id] = existing
                continue
            if turn.get("speaker") == "applicant" and turn_id in ranges:
                start_ms, end_ms, source_key = ranges[turn_id]
            else:
                next_answer = next(
                    (
                        ranges[_required_str(item, "turn_id")]
                        for item in turns[index + 1 :]
                        if item.get("speaker") == "applicant"
                        and _required_str(item, "turn_id") in ranges
                    ),
                    None,
                )
                if next_answer is None:
                    start_ms = synthetic_cursor
                    end_ms = start_ms + 1_000
                else:
                    end_ms = max(1, next_answer[0])
                    start_ms = max(0, end_ms - 1_000)
                source_key = f"question/{turn_id}"
            if end_ms <= start_ms:
                end_ms = start_ms + 1
            row = TranscriptSegmentRow(
                transcript_segment_id=str(self._id_generator.new()),
                company_id=str(context.company_id),
                interview_session_id=str(session_id),
                turn_id=turn_id,
                speaker=_required_str(turn, "speaker"),
                text=text,
                confidence=1.0,
                session_start_ms=start_ms,
                session_end_ms=end_ms,
                source_audio_key=source_key,
                version=1,
                corrected_by=None,
                created_at=self._clock.now(),
            )
            self._repository.add(context, row)
            rows_by_turn[turn_id] = row
        return rows_by_turn

    def _report_result(
        self,
        context: TenantContext,
        report: ReportRow,
    ) -> Mapping[str, object]:
        items = self._repository.report_items(context, report.report_id)
        counts = {
            "confirmed": 0,
            "partially_confirmed": 0,
            "insufficient_evidence": 0,
            "needs_follow_up": 0,
        }
        for item in items:
            if item.assessment_state in counts:
                counts[item.assessment_state] += 1
        return {
            "report_id": report.report_id,
            "report_version": report.report_version,
            "status": report.status,
            "confirmed_count": counts["confirmed"],
            "partially_confirmed_count": counts["partially_confirmed"],
            "insufficient_evidence_count": counts["insufficient_evidence"],
            "needs_follow_up_count": counts["needs_follow_up"],
        }


class SQLAlchemyReportingCompletionHandler:
    __slots__ = (
        "_clock",
        "_id_generator",
        "_interview_public",
        "_media",
        "_outbox",
        "_report",
        "_session",
    )

    def __init__(
        self,
        session: Session,
        *,
        interview_public: CompletedInterviewProvider,
        clock: Clock | None = None,
        id_generator: UUID7Generator | None = None,
    ) -> None:
        self._session = session
        self._interview_public = interview_public
        self._clock = clock or SystemClock()
        self._id_generator = id_generator or UUID7Generator(self._clock)
        self._outbox = SQLAlchemyOutbox(session)
        self._media = SQLAlchemyMediaPostprocessHandler(
            session,
            interview_public=interview_public,
            clock=self._clock,
            id_generator=self._id_generator,
        )
        self._report = SQLAlchemyReportGenerationHandler(
            session,
            interview_public=interview_public,
            clock=self._clock,
            id_generator=self._id_generator,
        )

    def handle_event(
        self,
        context: TenantContext,
        event: object,
    ) -> Mapping[str, object]:
        ensure_company_scope(context, context.company_id)
        if _event_type(event) != "interview.completed":
            raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
        payload = _event_payload(event)
        session_id = _required_id(payload, "interview_session_id")
        existing = self._session.scalar(
            select(ReportRow).where(
                ReportRow.company_id == str(context.company_id),
                ReportRow.interview_session_id == str(session_id),
                ReportRow.report_version == 1,
            )
        )
        if existing is not None:
            return self._report._report_result(context, existing)
        snapshot = self._interview_public.get_completed_session_snapshot(
            context,
            session_id=session_id,
        )
        model_version_id = _required_id(snapshot, "competency_model_version_id")
        asset_id = self._id_generator.new()
        media_event = self._add_event(
            context,
            source=event,
            event_type="media.postprocess_requested",
            aggregate_type="recording_asset",
            aggregate_id=asset_id,
            idempotency_key=f"media-postprocess:{session_id}:v1",
            payload={
                "interview_session_id": str(session_id),
                "ordered_chunk_set_id": str(session_id),
                "output_profile_version": "media-profile-v1",
            },
        )
        self._media.handle_event(context, media_event)
        self._outbox.mark_published(
            context,
            media_event.event_id,
            published_at=self._clock.now(),
        )
        report_id = self._id_generator.new()
        report_event = self._add_event(
            context,
            source=event,
            event_type="report.generation_requested",
            aggregate_type="report",
            aggregate_id=report_id,
            idempotency_key=f"report-generation:{session_id}:v1",
            payload={
                "interview_session_id": str(session_id),
                "report_version": 1,
                "competency_model_version_id": str(model_version_id),
            },
        )
        report_result = self._report.handle_event(context, report_event)
        self._outbox.mark_published(
            context,
            report_event.event_id,
            published_at=self._clock.now(),
        )
        ready_event = self._add_event(
            context,
            source=report_event,
            event_type="report.ready",
            aggregate_type="report",
            aggregate_id=report_id,
            idempotency_key=f"report-ready:{session_id}:v1",
            payload={
                "interview_session_id": str(session_id),
                **dict(report_result),
            },
        )
        self._outbox.mark_published(
            context,
            ready_event.event_id,
            published_at=self._clock.now(),
        )
        return report_result

    def _add_event(
        self,
        context: TenantContext,
        *,
        source: object,
        event_type: str,
        aggregate_type: str,
        aggregate_id: OpaqueId,
        idempotency_key: str,
        payload: Mapping[str, object],
    ) -> OutboxEvent:
        return self._outbox.add(
            context,
            OutboxEvent(
                event_id=self._id_generator.new(),
                company_id=context.company_id,
                event_type=event_type,
                event_version=1,
                aggregate=AggregateRef(
                    aggregate_type=aggregate_type,
                    aggregate_id=aggregate_id,
                    version=1,
                ),
                idempotency_key=idempotency_key,
                occurred_at=self._clock.now(),
                trace_id=context.trace_id,
                correlation_id=_event_correlation_id(source, context),
                causation_id=_event_id(source),
                payload=cast(Mapping[str, FrozenValue], payload),
            ),
        )


class SQLAlchemyReportingQueueHandler:
    __slots__ = ("_event_type", "_session_factory")

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        event_type: str,
    ) -> None:
        self._session_factory = session_factory
        self._event_type = event_type

    def handle_event(
        self,
        context: TenantContext,
        event: object,
    ) -> Mapping[str, object]:
        from interview_evidence.interview_engine.contracts import (
            InterviewEvidencePublicService,
        )
        from interview_evidence.interview_engine.repositories.postgres import (
            InterviewSessionRepository,
        )

        with self._session_factory.begin() as session:
            public = InterviewEvidencePublicService(InterviewSessionRepository(session))
            if self._event_type == "interview.completed":
                result = SQLAlchemyReportingCompletionHandler(
                    session, interview_public=public
                ).handle_event(context, event)
            elif self._event_type == "media.postprocess_requested":
                result = SQLAlchemyMediaPostprocessHandler(
                    session, interview_public=public
                ).handle_event(context, event)
            elif self._event_type == "report.generation_requested":
                result = SQLAlchemyReportGenerationHandler(
                    session, interview_public=public
                ).handle_event(context, event)
            else:
                raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
            if not isinstance(result, Mapping):
                raise SafeApplicationError(ErrorCode.INTERNAL_ERROR)
            return result


def _event_type(event: object) -> str:
    value = getattr(event, "event_type", None)
    if not isinstance(value, str):
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
    return value


def _event_payload(event: object) -> Mapping[str, object]:
    value = getattr(event, "payload", None)
    if not isinstance(value, Mapping):
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
    return value


def _event_id(event: object) -> OpaqueId:
    value = getattr(event, "event_id", None)
    try:
        return OpaqueId(str(value))
    except ValueError:
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None


def _event_correlation_id(event: object, context: TenantContext) -> OpaqueId:
    value = getattr(event, "correlation_id", context.request_id)
    try:
        return OpaqueId(str(value))
    except ValueError:
        return context.request_id


def _event_aggregate_id(event: object) -> OpaqueId:
    aggregate = getattr(event, "aggregate", None)
    value = getattr(aggregate, "aggregate_id", None)
    if value is None:
        value = getattr(event, "aggregate_id", None)
    try:
        return OpaqueId(str(value))
    except ValueError:
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None


def _mapping_items(value: Mapping[str, object], key: str) -> list[Mapping[str, object]]:
    items = value.get(key)
    if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
    return list(items)


def _required_id(value: Mapping[str, object], key: str) -> OpaqueId:
    try:
        return OpaqueId(_required_str(value, key))
    except ValueError:
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from None


def _required_str(value: Mapping[str, object] | None, key: str) -> str:
    if value is None:
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
    item = value.get(key)
    if not isinstance(item, str):
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
    return item


def _required_int(value: Mapping[str, object], key: str) -> int:
    item = value.get(key)
    if not isinstance(item, int):
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
    return item


def _media_available(asset: RecordingAssetRow, start_ms: int, end_ms: int) -> bool:
    if asset.status not in {"ready", "partial"}:
        return False
    if not 0 <= start_ms < end_ms <= asset.duration_ms:
        return False
    return not any(
        start_ms < missing_end and end_ms > missing_start
        for missing_start, missing_end in asset.missing_ranges
    )
