from __future__ import annotations

from collections.abc import Callable

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from interview_evidence.reporting.api.company_routes import ReportingRouteRuntime
from interview_evidence.reporting.repositories.postgres import (
    DeletionManifestRow,
    DeletionRequestRow,
    DeletionTargetRow,
    HumanReviewRow,
    ReportingRepository,
    ReportRow,
)
from interview_evidence.shared.audit import InMemoryAuditAppender
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, SystemClock, UUID7Generator
from interview_evidence.shared.tenant import ActorType, TenantContext, ensure_company_scope


class SQLAlchemyReportingRouteService:
    __slots__ = ("_clock", "_id_generator", "_repository", "_session")

    def __init__(
        self,
        session: Session,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self._session = session
        self._repository = ReportingRepository(session)
        self._clock = clock
        self._id_generator = id_generator

    def get_report(self, **arguments: object) -> dict[str, object]:
        context = self._context(arguments)
        session_id = str(OpaqueId(str(arguments["session_id"])))
        report = self._session.scalar(
            select(ReportRow).where(
                ReportRow.company_id == str(context.company_id),
                ReportRow.interview_session_id == session_id,
            )
        )
        if report is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        items = []
        for item in self._repository.report_items(context, report.report_id):
            evidence = [
                {
                    "evidence_id": row.evidence_id,
                    "answer_turn_id": row.answer_turn_id,
                    "transcript_segment_id": row.transcript_segment_id,
                    "video_start_ms": row.video_start_ms,
                    "video_end_ms": row.video_end_ms,
                    "observation": row.observation,
                    "rationale": row.rationale,
                    "sufficiency": row.sufficiency,
                }
                for row in self._repository.evidence_rows(context, item.report_item_id)
            ]
            items.append(
                {
                    "report_item_id": item.report_item_id,
                    "criterion_id": item.criterion_id,
                    "assessment_state": item.assessment_state,
                    "observation": item.observation,
                    "rationale": item.rationale,
                    "uncertainty": item.uncertainty,
                    "follow_up_question": item.follow_up_question,
                    "evidence": evidence,
                }
            )
        reviews = [
            self._review_view(row)
            for row in self._repository.human_review_rows(context, report.report_id)
        ]
        return {
            "report_id": report.report_id,
            "report_version": report.report_version,
            "status": report.status,
            "summary": report.summary,
            "items": items,
            "ai_original_immutable": True,
            "human_reviews": reviews,
        }

    def get_timeline(self, **arguments: object) -> dict[str, object]:
        context = self._context(arguments)
        session_id = str(OpaqueId(str(arguments["session_id"])))
        query = arguments.get("query")
        entries: list[dict[str, object]] = []
        for segment in self._repository.transcript_rows(context, session_id):
            if isinstance(query, str) and query.casefold() not in segment.text.casefold():
                continue
            entries.append(
                {
                    "entry_id": segment.transcript_segment_id,
                    "entry_type": "question" if segment.speaker == "interviewer" else "answer",
                    "start_ms": segment.session_start_ms,
                    "end_ms": segment.session_end_ms,
                    "text": segment.text,
                    "technical_failure": False,
                }
            )
        for event in self._repository.session_event_rows(context, session_id):
            entries.append(
                {
                    "entry_id": event.session_event_id,
                    "entry_type": "event",
                    "start_ms": event.session_start_ms,
                    "end_ms": event.session_end_ms,
                    "text": None,
                    "technical_failure": event.technical_failure,
                }
            )
        entries.sort(key=self._timeline_sort_key)
        assets = self._repository.recording_asset_rows(context, session_id)
        ready = next((asset for asset in assets if asset.status == "ready"), None)
        return {
            "entries": entries,
            "playback": {
                "url": None,
                "expires_at": None,
                "status": "ready" if ready is not None else "unavailable",
            },
        }

    def create_review(self, **arguments: object) -> dict[str, object]:
        context = self._context(arguments)
        report_id = OpaqueId(str(arguments["report_id"]))
        report_item_id = OpaqueId(str(arguments["report_item_id"]))
        self._repository.report_row(context, report_id)
        return self._append_review(
            context,
            report_id=report_id,
            target_id=report_item_id,
            review_type="assessment_override",
            value={"assessment_state": str(arguments["assessment_state"])},
            reason=str(arguments["reason"]),
            idempotency_key=str(arguments["idempotency_key"]),
        )

    def create_artifact(self, **arguments: object) -> dict[str, object]:
        context = self._context(arguments)
        target_id = OpaqueId(str(arguments["target_id"]))
        raw_value = arguments["value"]
        if not isinstance(raw_value, dict):
            raise TypeError("review artifact value must be an object")
        return self._append_review(
            context,
            report_id=OpaqueId(str(arguments["session_id"])),
            target_id=target_id,
            review_type=str(arguments["review_type"]),
            value=dict(raw_value),
            reason=(str(arguments["reason"]) if arguments.get("reason") is not None else None),
            idempotency_key=str(arguments["idempotency_key"]),
        )

    def final_decision(self, **arguments: object) -> dict[str, object]:
        context = self._context(arguments)
        if context.actor_type is not ActorType.COMPANY_USER:
            raise SafeApplicationError(ErrorCode.FORBIDDEN)
        invitation_id = OpaqueId(str(arguments["invitation_id"]))
        return self._append_review(
            context,
            report_id=invitation_id,
            target_id=invitation_id,
            review_type="final_decision",
            value={"decision": str(arguments["decision"])},
            reason=str(arguments["reason"]),
            idempotency_key=str(arguments["idempotency_key"]),
        )

    def request_deletion(self, **arguments: object) -> dict[str, object]:
        context = self._context(arguments)
        deletion_request_id = self._id_generator.new()
        manifest_id = self._id_generator.new()
        self._session.add(
            DeletionRequestRow(
                deletion_request_id=str(deletion_request_id),
                company_id=str(context.company_id),
                applicant_id=str(context.actor_id),
                invitation_id=str(context.actor_id),
                reason=str(arguments["reason"]),
                policy_snapshot={"version": 1},
                status="requested",
                requested_at=self._clock.now(),
            )
        )
        self._session.add(
            DeletionManifestRow(
                manifest_id=str(manifest_id),
                company_id=str(context.company_id),
                deletion_request_id=str(deletion_request_id),
                manifest_version=1,
                status="requested",
            )
        )
        self._session.flush()
        return self._deletion_view(context, deletion_request_id)

    def deletion_status(self, **arguments: object) -> dict[str, object]:
        context = self._context(arguments)
        return self._deletion_view(
            context,
            OpaqueId(str(arguments["deletion_request_id"])),
        )

    def _append_review(
        self,
        context: TenantContext,
        *,
        report_id: OpaqueId,
        target_id: OpaqueId,
        review_type: str,
        value: dict[str, object],
        reason: str | None,
        idempotency_key: str,
    ) -> dict[str, object]:
        existing = self._session.scalar(
            select(HumanReviewRow).where(
                HumanReviewRow.company_id == str(context.company_id),
                HumanReviewRow.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            ensure_company_scope(context, existing.company_id)
            return self._review_view(existing)
        review = HumanReviewRow(
            human_review_id=str(self._id_generator.new()),
            company_id=str(context.company_id),
            report_id=str(report_id),
            company_user_id=str(context.actor_id),
            review_type=review_type,
            target_id=str(target_id),
            value=value,
            reason=reason,
            idempotency_key=idempotency_key,
            created_at=self._clock.now(),
        )
        self._session.add(review)
        self._session.flush()
        return self._review_view(review)

    def _deletion_view(
        self,
        context: TenantContext,
        deletion_request_id: OpaqueId,
    ) -> dict[str, object]:
        request = self._repository.deletion_request_row(context, deletion_request_id)
        manifest = self._repository.deletion_manifest_row(context, deletion_request_id)
        targets = self._session.scalars(
            select(DeletionTargetRow)
            .where(
                DeletionTargetRow.company_id == str(context.company_id),
                DeletionTargetRow.manifest_id == manifest.manifest_id,
            )
            .order_by(DeletionTargetRow.target_id)
        ).all()
        target_views = [
            {
                "target_id": row.target_id,
                "owner_lane": row.owner_lane,
                "store": row.store,
                "target_type": row.target_type,
                "status": row.status,
                "attempts": row.attempts,
                "verified_at": (
                    row.verified_at.isoformat().replace("+00:00", "Z")
                    if row.verified_at is not None
                    else None
                ),
                "error_code": row.last_error_code,
            }
            for row in targets
        ]
        return {
            "deletion_request_id": request.deletion_request_id,
            "manifest_id": manifest.manifest_id,
            "status": request.status,
            "expected_targets": len(target_views),
            "verified_targets": sum(
                target["status"] == "verified_absent" for target in target_views
            ),
            "targets": target_views,
        }

    @staticmethod
    def _review_view(row: HumanReviewRow) -> dict[str, object]:
        return {
            "human_review_id": row.human_review_id,
            "review_type": row.review_type,
            "created_by": row.company_user_id,
            "created_at": row.created_at.isoformat().replace("+00:00", "Z"),
        }

    @staticmethod
    def _context(arguments: dict[str, object]) -> TenantContext:
        context = arguments["context"]
        if not isinstance(context, TenantContext):
            raise TypeError("tenant context is required")
        return ensure_company_scope(context, context.company_id)

    @staticmethod
    def _timeline_sort_key(entry: dict[str, object]) -> tuple[int, str]:
        start_ms = entry["start_ms"]
        if not isinstance(start_ms, int):
            raise TypeError("timeline start_ms must be an integer")
        return start_ms, str(entry["entry_id"])


def create_reporting_runtime(
    session: Session,
    *,
    context_provider: Callable[[Request], TenantContext],
    clock: Clock | None = None,
) -> ReportingRouteRuntime:
    active_clock = clock or SystemClock()
    id_generator = UUID7Generator(active_clock)
    return ReportingRouteRuntime(
        service=SQLAlchemyReportingRouteService(
            session,
            clock=active_clock,
            id_generator=id_generator,
        ),
        context_provider=context_provider,
        audit_appender=InMemoryAuditAppender(
            clock=active_clock,
            id_generator=id_generator,
        ),
    )
