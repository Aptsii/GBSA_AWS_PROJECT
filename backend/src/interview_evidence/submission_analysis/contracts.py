from __future__ import annotations

from dataclasses import dataclass

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope
from interview_evidence.submission_analysis.application.deletion_targets import (
    SubmissionDeletionService,
    SubmissionDeletionTarget,
)
from interview_evidence.submission_analysis.application.retrieval import (
    HybridRetriever,
    RetrievalQuery,
)
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)


@dataclass(slots=True)
class SubmissionAnalysisPublicService:
    repository: SubmissionAnalysisRepository
    retriever: HybridRetriever
    deletion: SubmissionDeletionService

    def get_analysis_status(
        self, context: TenantContext, *, invitation_id: str | OpaqueId
    ) -> dict[str, object]:
        scope = self.repository.scope_for_invitation(context, invitation_id)
        submissions = self.repository.list_submissions(context, scope)
        strategy = self.repository.latest_strategy(context, scope)
        statuses = {submission.status.value for submission in submissions}
        if not submissions:
            overall_status = "waiting"
        elif statuses <= {"ready"}:
            overall_status = "ready"
        elif "partial" in statuses or ("failed" in statuses and len(statuses) > 1):
            overall_status = "partial"
        elif statuses == {"failed"}:
            overall_status = "failed"
        else:
            overall_status = "analyzing"
        return {
            "company_id": str(scope.company_id),
            "invitation_id": str(scope.invitation_id),
            "overall_status": overall_status,
            "submissions": [
                {
                    "submission_id": str(submission.submission_id),
                    "status": submission.status.value,
                    "impact_code": submission.failure_code,
                }
                for submission in submissions
            ],
            "strategy_ready": strategy is not None,
        }

    def get_strategy_snapshot(
        self, context: TenantContext, *, strategy_id: str | OpaqueId
    ) -> dict[str, object]:
        return self.repository.get_strategy(context, strategy_id).snapshot()

    def retrieve_context(
        self,
        context: TenantContext,
        *,
        scope: ApplicantScope,
        query_text: str,
        query_vector: tuple[float, ...],
        criterion_id: str | OpaqueId,
        interview_session_id: str | OpaqueId,
        config_version: str,
        exact_symbol: str | None = None,
        limit: int = 10,
    ) -> dict[str, object]:
        ensure_applicant_scope(context, scope)
        result = self.retriever.retrieve(
            context,
            RetrievalQuery(
                scope=scope,
                query_text=query_text,
                query_vector=query_vector,
                criterion_id=OpaqueId(criterion_id),
                interview_session_id=OpaqueId(interview_session_id),
                config_version=config_version,
                exact_symbol=exact_symbol,
                limit=limit,
            ),
        )
        return {
            "company_id": str(result.company_id),
            "applicant_id": str(result.applicant_id),
            "interview_session_id": str(result.interview_session_id),
            "criterion_id": str(result.criterion_id),
            "retrieval_config_version": result.retrieval_config_version,
            "results": [
                {
                    "rank": item.rank,
                    "score": item.score,
                    "source_reference": item.source_reference.snapshot(),
                }
                for item in result.results
            ],
        }

    def resolve_source_reference(
        self, context: TenantContext, *, source_id: str | OpaqueId
    ) -> dict[str, object]:
        return self.repository.get_source_reference(context, source_id).snapshot()

    def enumerate_submission_deletion_targets(
        self, context: TenantContext, *, scope: ApplicantScope
    ) -> dict[str, object]:
        targets = self.deletion.enumerate_targets(context, scope)
        return {
            "company_id": str(scope.company_id),
            "scope_type": "invitation",
            "scope_id": str(scope.invitation_id),
            "owner_lane": "B",
            "targets": [
                {
                    "target_id": str(target.target_id),
                    "target_type": target.target_type,
                    "store": target.store,
                    "target_version": target.target_version,
                }
                for target in targets
            ],
        }

    def delete_submission_target(
        self,
        context: TenantContext,
        *,
        scope: ApplicantScope,
        deletion_request_id: str | OpaqueId,
        target: SubmissionDeletionTarget,
    ) -> dict[str, object]:
        receipt = self.deletion.delete_target(context, scope, target)
        return {
            "company_id": str(receipt.company_id),
            "deletion_request_id": str(OpaqueId(deletion_request_id)),
            "target_id": str(receipt.target_id),
            "owner_lane": receipt.owner_lane,
            "status": receipt.status,
            "attempts": receipt.attempts,
            "verified_at": receipt.verified_at.isoformat() if receipt.verified_at else None,
            "error_code": receipt.error_code,
        }
