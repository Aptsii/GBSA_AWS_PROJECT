from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from interview_evidence.shared.database import Base
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import (
    ApplicantScope,
    TenantContext,
    TenantScopeViolation,
    ensure_applicant_scope,
)
from interview_evidence.submission_analysis.domain.source import SourceLocation, SourceReference
from interview_evidence.submission_analysis.domain.strategy import (
    InterviewStrategy,
    SourceReferenceCandidate,
    StrategyStatus,
)
from interview_evidence.submission_analysis.domain.submission import (
    SourceType,
    Submission,
    SubmissionStatus,
)
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    select,
)
from sqlalchemy.orm import Mapped, Session, mapped_column


class SubmissionRow(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("company_id", "submission_id", name="uq_submissions_company_submission"),
    )

    submission_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invitation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_uri: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_hash: Mapped[str | None] = mapped_column(String(64))
    byte_size: Mapped[int | None] = mapped_column(Integer)
    media_type: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(128))
    impact_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SubmissionAnalysisRow(Base):
    __tablename__ = "submission_analyses"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "submission_id", "analysis_version", name="uq_submission_analysis_version"
        ),
    )

    analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    analysis_version: Mapped[int] = mapped_column(Integer, nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(128), nullable=False)
    chunk_config_version: Mapped[str] = mapped_column(String(128), nullable=False)
    claims: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    conflicts: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    verification_points: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SubmissionSourceReferenceRow(Base):
    __tablename__ = "submission_source_references"

    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invitation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_location: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    ownership_confidence: Mapped[float | None] = mapped_column(Float)
    evidence_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class GitRepositoryAnalysisRow(Base):
    __tablename__ = "git_repository_analyses"

    repository_analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    submission_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    repository_url: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    pinned_head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    candidate_identity_inputs: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    limits_applied: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class GitCommitAnalysisRow(Base):
    __tablename__ = "git_commit_analyses"

    git_commit_analysis_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    repository_analysis_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    parent_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    author_match_inputs: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    change_summary_object_id: Mapped[str] = mapped_column(String(36), nullable=False)
    ownership_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ownership_class: Mapped[str] = mapped_column(String(32), nullable=False)


class CandidateCodeUnitRow(Base):
    __tablename__ = "candidate_code_units"

    code_unit_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    git_commit_analysis_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(Text, nullable=False)
    original_line_range: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    current_line_range: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    candidate_owned_regions: Mapped[list[list[int]]] = mapped_column(JSON, nullable=False)
    related_test_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dependency_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    index_document_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)


class InterviewStrategyRow(Base):
    __tablename__ = "interview_strategies"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "invitation_id", "strategy_version", name="uq_strategy_invitation_version"
        ),
    )

    interview_strategy_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    invitation_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    competency_model_version_id: Mapped[str] = mapped_column(String(36), nullable=False)
    strategy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    common_topics: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    verification_points: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    follow_up_directions: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    time_budget: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    required_evidence_plan: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    source_reference_candidates: Mapped[list[dict[str, object]]] = mapped_column(
        JSON, nullable=False
    )
    model_config_version: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SubmissionAnalysisRepository:
    __slots__ = ("session",)

    def __init__(self, session: Session) -> None:
        self.session = session

    def add_submission(self, context: TenantContext, submission: Submission) -> Submission:
        ensure_applicant_scope(context, submission.scope)
        self.session.merge(self._submission_row(submission))
        self.session.flush()
        return submission

    def get_submission(self, context: TenantContext, submission_id: str | OpaqueId) -> Submission:
        checked_id = OpaqueId(submission_id)
        row = self.session.get(SubmissionRow, str(checked_id))
        if row is None:
            raise SafeApplicationError(ErrorCode.RESOURCE_NOT_FOUND)
        if row.company_id != str(context.company_id):
            raise TenantScopeViolation
        return self._submission(row)

    def list_submissions(
        self, context: TenantContext, scope: ApplicantScope
    ) -> tuple[Submission, ...]:
        ensure_applicant_scope(context, scope)
        rows = self.session.scalars(
            select(SubmissionRow)
            .where(
                SubmissionRow.company_id == str(scope.company_id),
                SubmissionRow.applicant_id == str(scope.applicant_id),
                SubmissionRow.invitation_id == str(scope.invitation_id),
            )
            .order_by(SubmissionRow.created_at, SubmissionRow.submission_id)
        ).all()
        return tuple(self._submission(row) for row in rows)

    def mark_submission_ready(
        self, context: TenantContext, submission_id: str | OpaqueId
    ) -> Submission:
        submission = self.get_submission(context, submission_id)
        if submission.status is SubmissionStatus.RECEIVED:
            submission = submission.transition(SubmissionStatus.VALIDATING)
        if submission.status is SubmissionStatus.VALIDATING:
            submission = submission.transition(SubmissionStatus.ANALYZING)
        if submission.status is SubmissionStatus.ANALYZING:
            submission = submission.transition(SubmissionStatus.READY)
        return self.add_submission(context, submission)

    def record_source_reference(
        self,
        context: TenantContext,
        scope: ApplicantScope,
        *,
        submission_id: str | OpaqueId,
        reference: SourceReference,
    ) -> SourceReference:
        ensure_applicant_scope(context, scope)
        self.get_submission(context, submission_id)
        self.session.merge(
            SubmissionSourceReferenceRow(
                source_id=str(reference.source_id),
                company_id=str(scope.company_id),
                invitation_id=str(scope.invitation_id),
                applicant_id=str(scope.applicant_id),
                submission_id=str(OpaqueId(submission_id)),
                source_type=reference.source_type,
                source_version=reference.source_version,
                source_location=reference.source_location.as_dict(),
                source_hash=reference.source_hash,
                ownership_confidence=reference.ownership_confidence,
                evidence_eligible=False,
            )
        )
        self.session.flush()
        return reference

    def list_source_references(
        self, context: TenantContext, scope: ApplicantScope
    ) -> tuple[SourceReference, ...]:
        ensure_applicant_scope(context, scope)
        rows = self.session.scalars(
            select(SubmissionSourceReferenceRow).where(
                SubmissionSourceReferenceRow.company_id == str(scope.company_id),
                SubmissionSourceReferenceRow.applicant_id == str(scope.applicant_id),
                SubmissionSourceReferenceRow.invitation_id == str(scope.invitation_id),
            )
        ).all()
        return tuple(self._source_reference(row) for row in rows)

    def add_strategy(
        self, context: TenantContext, strategy: InterviewStrategy
    ) -> InterviewStrategy:
        if strategy.company_id != context.company_id:
            raise TenantScopeViolation
        self.session.merge(self._strategy_row(strategy))
        self.session.flush()
        return strategy

    def latest_strategy(
        self, context: TenantContext, scope: ApplicantScope
    ) -> InterviewStrategy | None:
        ensure_applicant_scope(context, scope)
        row = self.session.scalars(
            select(InterviewStrategyRow)
            .where(
                InterviewStrategyRow.company_id == str(scope.company_id),
                InterviewStrategyRow.invitation_id == str(scope.invitation_id),
            )
            .order_by(InterviewStrategyRow.strategy_version.desc())
        ).first()
        return self._strategy(row) if row else None

    def relational_target_ids(
        self, context: TenantContext, scope: ApplicantScope
    ) -> tuple[OpaqueId, ...]:
        return tuple(item.submission_id for item in self.list_submissions(context, scope))

    def delete_relational_target(
        self, context: TenantContext, scope: ApplicantScope, target_id: str | OpaqueId
    ) -> bool:
        ensure_applicant_scope(context, scope)
        checked_id = str(OpaqueId(target_id))
        submission = self.get_submission(context, checked_id)
        if submission.scope != scope:
            raise TenantScopeViolation
        self.session.execute(
            delete(SubmissionSourceReferenceRow).where(
                SubmissionSourceReferenceRow.submission_id == checked_id,
                SubmissionSourceReferenceRow.company_id == str(scope.company_id),
            )
        )
        self.session.execute(
            delete(SubmissionRow).where(
                SubmissionRow.submission_id == checked_id,
                SubmissionRow.company_id == str(scope.company_id),
            )
        )
        self.session.flush()
        return self.session.get(SubmissionRow, checked_id) is None

    @staticmethod
    def _submission_row(submission: Submission) -> SubmissionRow:
        return SubmissionRow(
            submission_id=str(submission.submission_id),
            company_id=str(submission.scope.company_id),
            invitation_id=str(submission.scope.invitation_id),
            applicant_id=str(submission.scope.applicant_id),
            source_type=submission.source_type.value,
            source_uri=submission.source_uri,
            original_filename=submission.original_filename,
            content_hash=submission.content_hash,
            byte_size=submission.byte_size,
            media_type=submission.media_type,
            status=submission.status.value,
            failure_code=submission.failure_code,
            impact_summary=submission.impact_summary,
            created_at=submission.created_at,
        )

    @staticmethod
    def _submission(row: SubmissionRow) -> Submission:
        return Submission(
            submission_id=OpaqueId(row.submission_id),
            scope=ApplicantScope(row.company_id, row.applicant_id, row.invitation_id),
            source_type=SourceType(row.source_type),
            source_uri=row.source_uri,
            original_filename=row.original_filename,
            content_hash=row.content_hash,
            byte_size=row.byte_size,
            media_type=row.media_type,
            status=SubmissionStatus(row.status),
            failure_code=row.failure_code,
            impact_summary=row.impact_summary,
            created_at=_instant(row.created_at),
        )

    @staticmethod
    def _source_reference(row: SubmissionSourceReferenceRow) -> SourceReference:
        allowed = {
            key: value
            for key, value in row.source_location.items()
            if key in SourceLocation.__dataclass_fields__
        }
        return SourceReference(
            company_id=OpaqueId(row.company_id),
            source_type=row.source_type,  # type: ignore[arg-type]
            source_id=OpaqueId(row.source_id),
            source_version=row.source_version,
            source_location=SourceLocation(**allowed),
            source_hash=row.source_hash,
            ownership_confidence=row.ownership_confidence,
        )

    @staticmethod
    def _strategy_row(strategy: InterviewStrategy) -> InterviewStrategyRow:
        return InterviewStrategyRow(
            interview_strategy_id=str(strategy.interview_strategy_id),
            company_id=str(strategy.company_id),
            invitation_id=str(strategy.invitation_id),
            competency_model_version_id=str(strategy.competency_model_version_id),
            strategy_version=strategy.strategy_version,
            common_topics=list(strategy.common_topics),
            verification_points=list(strategy.verification_points),
            follow_up_directions=strategy.follow_up_directions,
            time_budget=strategy.time_budget,
            required_evidence_plan=strategy.required_evidence_plan,
            source_reference_candidates=[
                {
                    "source_type": item.source_type,
                    "source_id": str(item.source_id),
                    "locator_version": item.locator_version,
                }
                for item in strategy.source_reference_candidates
            ],
            model_config_version=strategy.model_config_version,
            status=strategy.status.value,
            created_at=strategy.created_at,
        )

    @staticmethod
    def _strategy(row: InterviewStrategyRow) -> InterviewStrategy:
        return InterviewStrategy(
            interview_strategy_id=OpaqueId(row.interview_strategy_id),
            company_id=OpaqueId(row.company_id),
            invitation_id=OpaqueId(row.invitation_id),
            competency_model_version_id=OpaqueId(row.competency_model_version_id),
            strategy_version=row.strategy_version,
            common_topics=tuple(row.common_topics),
            verification_points=tuple(row.verification_points),
            follow_up_directions=row.follow_up_directions,
            time_budget=row.time_budget,
            required_evidence_plan=row.required_evidence_plan,
            source_reference_candidates=tuple(
                SourceReferenceCandidate(
                    source_type=item["source_type"],  # type: ignore[arg-type]
                    source_id=OpaqueId(str(item["source_id"])),
                    locator_version=int(item["locator_version"]),
                )
                for item in row.source_reference_candidates
            ),
            model_config_version=row.model_config_version,
            status=StrategyStatus(row.status),
            created_at=_instant(row.created_at),
        )


def _instant(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
