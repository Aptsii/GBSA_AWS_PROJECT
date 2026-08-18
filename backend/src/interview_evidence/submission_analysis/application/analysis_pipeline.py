from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, UUID7Generator
from interview_evidence.shared.messaging.outbox import AggregateRef, OutboxEvent
from interview_evidence.shared.persistence import SQLAlchemyOutbox
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope
from interview_evidence.submission_analysis.adapters.object_storage import SubmissionObjectStorage
from interview_evidence.submission_analysis.application.authorization import (
    CompanyAuthorizationContracts,
)
from interview_evidence.submission_analysis.application.strategy_service import StrategyService
from interview_evidence.submission_analysis.domain.source import SourceLocation, SourceReference
from interview_evidence.submission_analysis.domain.submission import (
    AnalysisStatus,
    SourceType,
    Submission,
    SubmissionAnalysis,
    SubmissionStatus,
)
from interview_evidence.submission_analysis.repositories.postgres import (
    SubmissionAnalysisRepository,
)
from interview_evidence.workers.analysis.document_chunker import DocumentChunker
from interview_evidence.workers.analysis.document_extract import DocumentExtractor
from interview_evidence.workers.analysis.handlers import (
    AnalysisJob,
    AnalysisJobHandler,
    AnalysisOutcome,
)

CriterionSnapshotProvider = Callable[[TenantContext, ApplicantScope], Mapping[str, object]]


class CompanyCriterionSnapshotProvider:
    __slots__ = ("_contracts",)

    def __init__(self, contracts: CompanyAuthorizationContracts) -> None:
        self._contracts = contracts

    def __call__(
        self,
        context: TenantContext,
        scope: ApplicantScope,
    ) -> Mapping[str, object]:
        ensure_applicant_scope(context, scope)
        invitation = self._contracts.authorize_invitation(
            context,
            invitation_id=str(scope.invitation_id),
            required_state="consented",
        )
        campaign = self._contracts.get_campaign_snapshot(
            context,
            campaign_id=str(invitation["campaign_id"]),
        )
        criterion = self._contracts.get_criterion_version(
            context,
            version_id=str(campaign["competency_model_version_id"]),
        )
        if criterion.get("company_id") != str(scope.company_id):
            raise SafeApplicationError(ErrorCode.TENANT_SCOPE_DENIED)
        return {
            **criterion,
            "interview_duration_minutes": campaign.get("interview_duration_minutes", 30),
        }


class SubmissionAnalysisCoordinator:
    __slots__ = (
        "_clock",
        "_criterion_snapshot_provider",
        "_document_chunker",
        "_document_extractor",
        "_handler",
        "_id_generator",
        "_object_storage",
        "_outbox",
        "_repository",
        "_strategy_service",
    )

    def __init__(
        self,
        *,
        repository: SubmissionAnalysisRepository,
        object_storage: SubmissionObjectStorage,
        criterion_snapshot_provider: CriterionSnapshotProvider,
        outbox: SQLAlchemyOutbox,
        clock: Clock,
        id_generator: UUID7Generator,
        handler: AnalysisJobHandler | None = None,
    ) -> None:
        self._repository = repository
        self._object_storage = object_storage
        self._criterion_snapshot_provider = criterion_snapshot_provider
        self._outbox = outbox
        self._clock = clock
        self._id_generator = id_generator
        self._handler = handler or AnalysisJobHandler(clock=clock, id_generator=id_generator)
        self._document_extractor = DocumentExtractor()
        self._document_chunker = DocumentChunker()
        self._strategy_service = StrategyService(clock=clock, id_generator=id_generator)

    def dispatch(
        self,
        context: TenantContext,
        *,
        submission: Submission,
        upload_id: str | None,
        idempotency_key: str,
    ) -> Submission:
        ensure_applicant_scope(context, submission.scope)
        event = self._outbox.add(
            context,
            OutboxEvent(
                event_id=self._id_generator.new(),
                company_id=submission.scope.company_id,
                event_type="submission.analysis_requested",
                event_version=1,
                aggregate=AggregateRef(
                    aggregate_type="submission",
                    aggregate_id=submission.submission_id,
                    version=1,
                ),
                idempotency_key=idempotency_key,
                occurred_at=self._clock.now(),
                trace_id=context.trace_id,
                correlation_id=context.request_id,
                causation_id=None,
                payload={
                    "submission_id": str(submission.submission_id),
                    "analysis_version": 1,
                    "source_type": submission.source_type.value,
                    "source_object_id": (
                        submission.source_uri.removeprefix("object:")
                        if submission.source_uri.startswith("object:")
                        else None
                    ),
                    "limits_config_version": "analysis-limits-v1",
                },
            ),
        )
        completed = self.execute(
            context,
            submission=submission,
            upload_id=upload_id,
            idempotency_key=idempotency_key,
        )
        self._outbox.mark_published(context, event.event_id, published_at=self._clock.now())
        return completed

    def execute(
        self,
        context: TenantContext,
        *,
        submission: Submission,
        upload_id: str | None,
        idempotency_key: str,
    ) -> Submission:
        ensure_applicant_scope(context, submission.scope)
        existing = self._repository.latest_analysis(context, submission.submission_id)
        if existing is not None:
            return self._repository.get_submission(context, submission.submission_id)
        self._repository.mark_submission_analyzing(context, submission.submission_id)
        verification_points: tuple[dict[str, object], ...] = ()

        def process(job: AnalysisJob) -> AnalysisOutcome:
            nonlocal verification_points
            try:
                references, partial, impact_code = self._source_references(
                    context,
                    submission,
                    upload_id=upload_id,
                )
                criterion_snapshot = self._criterion_snapshot_provider(context, submission.scope)
                verification_points = self._verification_points(criterion_snapshot, references)
                duration = criterion_snapshot.get("interview_duration_minutes", 30)
                if not isinstance(duration, int):
                    raise ValueError("interview duration must be an integer")
                strategy = self._strategy_service.generate(
                    context,
                    scope=submission.scope,
                    criterion_snapshot=criterion_snapshot,
                    verification_points=verification_points,
                    source_references=references,
                    duration_minutes=duration,
                    model_config_version="submission-strategy-v1",
                    partial=partial,
                )
                self._repository.add_strategy(context, strategy)
                return AnalysisOutcome(
                    status="partial" if partial else "ready",
                    impact_code=impact_code,
                )
            except SafeApplicationError:
                raise
            except (KeyError, TypeError, ValueError) as error:
                raise SafeApplicationError(ErrorCode.INVALID_REQUEST) from error

        outcome = self._handler.handle(
            context,
            AnalysisJob(
                company_id=submission.scope.company_id,
                scope=submission.scope,
                submission_id=submission.submission_id,
                analysis_version=1,
                source_type=submission.source_type.value,
                idempotency_key=idempotency_key,
            ),
            process,
        )
        if outcome.analysis_id is None:
            raise SafeApplicationError(ErrorCode.INTERNAL_ERROR)
        self._repository.add_analysis(
            context,
            SubmissionAnalysis(
                analysis_id=outcome.analysis_id,
                company_id=submission.scope.company_id,
                submission_id=submission.submission_id,
                analysis_version=1,
                extractor_version="document-extractor-v1",
                chunk_config_version="document-chunker-v1",
                claims=(),
                conflicts=(),
                verification_points=verification_points,
                status=AnalysisStatus(outcome.status),
                created_at=self._clock.now(),
            ),
        )
        completed = self._complete_submission(context, submission, outcome)
        return completed

    def _source_references(
        self,
        context: TenantContext,
        submission: Submission,
        *,
        upload_id: str | None,
    ) -> tuple[tuple[SourceReference, ...], bool, str | None]:
        if submission.source_type in {SourceType.COVER_LETTER, SourceType.RESUME, SourceType.PDF}:
            if submission.media_type is None:
                raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
            object_prefix, separator, object_id = submission.source_uri.partition(":")
            if object_prefix != "object" or separator != ":" or not object_id:
                raise SafeApplicationError(ErrorCode.INVALID_REQUEST)
            content = (
                self._object_storage.read_upload(context, submission.scope, upload_id)
                if upload_id is not None
                else self._object_storage.read_object(context, submission.scope, object_id)
            )
            document = self._document_extractor.extract(
                content,
                media_type=submission.media_type,
            )
            chunks = self._document_chunker.chunk(document)
            references = tuple(
                SourceReference(
                    company_id=submission.scope.company_id,
                    source_type="submission_chunk",
                    source_id=self._id_generator.new(),
                    source_version=1,
                    source_location=chunk.location,
                    source_hash=chunk.chunk_hash,
                )
                for chunk in chunks
            )
            for reference in references:
                self._repository.record_source_reference(
                    context,
                    submission.scope,
                    submission_id=submission.submission_id,
                    reference=reference,
                )
            if references:
                return references, False, None
            return (), True, "NO_EXTRACTABLE_CONTENT"

        source_hash = hashlib.sha256(submission.source_uri.encode()).hexdigest()
        reference = SourceReference(
            company_id=submission.scope.company_id,
            source_type="submission_chunk",
            source_id=self._id_generator.new(),
            source_version=1,
            source_location=SourceLocation(path="public-source"),
            source_hash=source_hash,
            ownership_confidence=0.5 if submission.source_type is SourceType.PUBLIC_GIT else None,
        )
        self._repository.record_source_reference(
            context,
            submission.scope,
            submission_id=submission.submission_id,
            reference=reference,
        )
        return (reference,), True, "PUBLIC_SOURCE_METADATA_ONLY"

    @staticmethod
    def _verification_points(
        criterion_snapshot: Mapping[str, object],
        references: tuple[SourceReference, ...],
    ) -> tuple[dict[str, object], ...]:
        criteria = criterion_snapshot.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise ValueError("criterion snapshot must contain criteria")
        source_ids = [str(reference.source_id) for reference in references]
        points: list[dict[str, object]] = []
        for item in criteria:
            if not isinstance(item, dict):
                continue
            points.append(
                {
                    "criterion_id": str(item["criterion_id"]),
                    "criterion_code": item.get("code"),
                    "prompt": f"{item.get('name', '역량')} 관련 경험의 근거를 설명해 주세요.",
                    "source_reference_ids": source_ids,
                }
            )
        if not points:
            raise ValueError("criterion snapshot must contain valid criteria")
        return tuple(points)

    def _complete_submission(
        self,
        context: TenantContext,
        submission: Submission,
        outcome: AnalysisOutcome,
    ) -> Submission:
        if outcome.status == "ready":
            return self._repository.complete_submission(
                context,
                submission.submission_id,
                status=SubmissionStatus.READY,
            )
        impact_code = outcome.impact_code or "ANALYSIS_INCOMPLETE"
        impact_summary = (
            "제출 자료에서 확인 가능한 내용만으로 면접 전략을 준비했습니다."
            if outcome.status == "partial"
            else "제출 자료 분석에 실패하여 면접 전략을 준비하지 못했습니다."
        )
        return self._repository.complete_submission(
            context,
            submission.submission_id,
            status=(
                SubmissionStatus.PARTIAL
                if outcome.status == "partial"
                else SubmissionStatus.FAILED
            ),
            failure_code=impact_code,
            impact_summary=impact_summary,
        )
