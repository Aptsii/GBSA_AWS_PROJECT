from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.adapters.search import InMemorySubmissionSearch
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)


@dataclass(frozen=True, slots=True)
class SubmissionDeletionTarget:
    target_id: OpaqueId
    target_type: str
    store: Literal["aurora", "s3", "opensearch"]
    target_version: int = 1


@dataclass(frozen=True, slots=True)
class SubmissionDeletionReceipt:
    company_id: OpaqueId
    target_id: OpaqueId
    owner_lane: Literal["B"]
    status: Literal["verified_absent", "failed"]
    attempts: int
    verified_at: datetime | None
    error_code: str | None


class SubmissionDeletionService:
    __slots__ = ("_objects", "_repository", "_search")

    def __init__(
        self,
        repository: SubmissionAnalysisRepository,
        objects: SubmissionObjectStorage,
        search: InMemorySubmissionSearch,
    ) -> None:
        self._repository = repository
        self._objects = objects
        self._search = search

    def enumerate_targets(
        self, context: TenantContext, scope: ApplicantScope
    ) -> tuple[SubmissionDeletionTarget, ...]:
        ensure_applicant_scope(context, scope)
        relational = tuple(
            SubmissionDeletionTarget(target_id, "submission", "aurora")
            for target_id in self._repository.relational_target_ids(context, scope)
        )
        objects = tuple(
            SubmissionDeletionTarget(target_id, "submission_original", "s3")
            for target_id in self._objects.upload_ids(context, scope)
        )
        search = tuple(
            SubmissionDeletionTarget(reference.source_id, reference.source_type, "opensearch")
            for reference in self._repository.list_source_references(context, scope)
        )
        return relational + objects + search

    def delete_target(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        target: SubmissionDeletionTarget,
    ) -> SubmissionDeletionReceipt:
        ensure_applicant_scope(context, scope)
        if target.store == "aurora":
            verified = self._repository.delete_relational_target(context, scope, target.target_id)
        elif target.store == "s3":
            verified = self._objects.delete_upload(context, scope, target.target_id)
        else:
            verified = self._search.delete(context, scope, target.target_id)
        return SubmissionDeletionReceipt(
            company_id=scope.company_id,
            target_id=target.target_id,
            owner_lane="B",
            status="verified_absent" if verified else "failed",
            attempts=1,
            verified_at=datetime.now(UTC) if verified else None,
            error_code=None if verified else "DELETE_NOT_VERIFIED",
        )
