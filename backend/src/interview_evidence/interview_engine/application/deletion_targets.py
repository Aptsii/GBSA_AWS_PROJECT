"""Lane C deletion target enumeration and verified absence receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from interview_evidence.interview_engine.adapters.recent_context import RecentContextView
from interview_evidence.interview_engine.application.recording_service import RecordingService
from interview_evidence.interview_engine.repositories.postgres import InterviewSessionRepository
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope


@dataclass(frozen=True, slots=True)
class InterviewDeletionTarget:
    target_id: OpaqueId
    target_type: str
    store: Literal["aurora", "dynamodb", "s3"]
    target_version: int = 1


@dataclass(frozen=True, slots=True)
class InterviewDeletionReceipt:
    company_id: OpaqueId
    target_id: OpaqueId
    owner_lane: Literal["C"]
    status: Literal["verified_absent", "failed"]
    attempts: int
    verified_at: datetime | None
    error_code: str | None


class InterviewDeletionService:
    __slots__ = ("_context_view", "_recordings", "_repository")

    def __init__(
        self,
        repository: InterviewSessionRepository,
        context_view: RecentContextView,
        recordings: RecordingService,
    ) -> None:
        self._repository = repository
        self._context_view = context_view
        self._recordings = recordings

    def enumerate_targets(
        self, context: TenantContext, scope: ApplicantScope
    ) -> tuple[InterviewDeletionTarget, ...]:
        ensure_applicant_scope(context, scope)
        relational = tuple(
            InterviewDeletionTarget(target_id, target_type, "aurora")
            for target_type, target_id in self._repository.relational_target_ids(context, scope)
        )
        hot_views = tuple(
            InterviewDeletionTarget(session_id, "recent_context", "dynamodb")
            for session_id in self._context_view.session_ids(context, scope)
        )
        media = tuple(
            InterviewDeletionTarget(chunk_id, "recording_object", "s3")
            for chunk_id in self._recordings.chunk_ids(context, scope)
        )
        return relational + hot_views + media

    def delete_target(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        target: InterviewDeletionTarget,
    ) -> InterviewDeletionReceipt:
        ensure_applicant_scope(context, scope)
        if target.store == "aurora":
            verified = self._repository.delete_relational_target(
                context, scope, target.target_type, target.target_id
            )
        elif target.store == "dynamodb":
            verified = self._context_view.delete(context, scope, target.target_id)
        else:
            verified = self._recordings.delete_chunk(context, scope, target.target_id)
        return InterviewDeletionReceipt(
            company_id=scope.company_id,
            target_id=target.target_id,
            owner_lane="C",
            status="verified_absent" if verified else "failed",
            attempts=1,
            verified_at=datetime.now(UTC) if verified else None,
            error_code=None if verified else "DELETE_NOT_VERIFIED",
        )
