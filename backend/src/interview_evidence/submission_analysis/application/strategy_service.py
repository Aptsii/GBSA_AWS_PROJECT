from __future__ import annotations

from collections.abc import Mapping

from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope
from interview_evidence.submission_analysis.domain.source import SourceReference
from interview_evidence.submission_analysis.domain.strategy import (
    InterviewStrategy,
    SourceReferenceCandidate,
    StrategyStatus,
)


class StrategyService:
    __slots__ = ("_clock", "_id_generator", "_versions")

    def __init__(self, *, clock: Clock, id_generator: UUID7Generator) -> None:
        self._clock = clock
        self._id_generator = id_generator
        self._versions: dict[tuple[OpaqueId, OpaqueId], int] = {}

    def generate(
        self,
        context: TenantContext,
        *,
        scope: ApplicantScope,
        criterion_snapshot: Mapping[str, object],
        verification_points: tuple[dict[str, object], ...],
        source_references: tuple[SourceReference, ...],
        duration_minutes: int,
        model_config_version: str,
        partial: bool,
    ) -> InterviewStrategy:
        ensure_applicant_scope(context, scope)
        if criterion_snapshot.get("company_id") != str(scope.company_id):
            raise ValueError("criterion snapshot belongs to another company")
        criteria_value = criterion_snapshot.get("criteria")
        if not isinstance(criteria_value, list) or not criteria_value:
            raise ValueError("criterion snapshot must contain criteria")
        criteria = [item for item in criteria_value if isinstance(item, dict)]
        allowed_ids = {str(item["criterion_id"]) for item in criteria}
        if any(str(point.get("criterion_id")) not in allowed_ids for point in verification_points):
            raise ValueError("verification point must use a fixed criterion")
        if any(reference.company_id != scope.company_id for reference in source_references):
            raise ValueError("source reference belongs to another company")
        version_key = (scope.company_id, scope.invitation_id)
        version = self._versions.get(version_key, 0) + 1
        self._versions[version_key] = version
        common_topics = tuple(
            {
                "criterion_id": str(item["criterion_id"]),
                "code": item.get("code"),
                "common_questions": item.get("common_questions", []),
            }
            for item in criteria
        )
        return InterviewStrategy(
            interview_strategy_id=self._id_generator.new(),
            company_id=scope.company_id,
            invitation_id=scope.invitation_id,
            competency_model_version_id=OpaqueId(
                str(criterion_snapshot["competency_model_version_id"])
            ),
            strategy_version=version,
            common_topics=common_topics,
            verification_points=verification_points,
            follow_up_directions={"max_per_topic": 2},
            time_budget={"minutes": duration_minutes},
            required_evidence_plan={
                "required_criteria": sum(bool(item.get("required")) for item in criteria)
            },
            source_reference_candidates=tuple(
                SourceReferenceCandidate(
                    source_type=reference.source_type,
                    source_id=reference.source_id,
                    locator_version=reference.source_version,
                )
                for reference in source_references
            ),
            model_config_version=model_config_version,
            status=StrategyStatus.PARTIAL if partial else StrategyStatus.READY,
            created_at=self._clock.now(),
        )
