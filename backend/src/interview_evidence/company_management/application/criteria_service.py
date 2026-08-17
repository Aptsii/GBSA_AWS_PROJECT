from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from interview_evidence.company_management.domain.criteria import (
    CompetencyModelVersion,
    EvaluationCriterion,
)
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
)
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import Clock, OpaqueId, UUID7Generator
from interview_evidence.shared.tenant import TenantContext


class CriteriaService:
    def __init__(
        self,
        repository: CompanyManagementRepository,
        *,
        clock: Clock,
        id_generator: UUID7Generator,
    ) -> None:
        self.repository = repository
        self.clock = clock
        self.id_generator = id_generator

    def create_version(
        self,
        context: TenantContext,
        *,
        position_id: str | OpaqueId,
        criteria: Sequence[Mapping[str, Any]],
        prohibited_topics: Sequence[str],
        interview_duration_minutes: int,
        persona_definition: Mapping[str, Any],
    ) -> CompetencyModelVersion:
        position = self.repository.get_position(context, position_id)
        version_id = self.id_generator.new()
        version = CompetencyModelVersion(
            competency_model_version_id=version_id,
            company_id=position.company_id,
            position_id=position.position_id,
            version_number=self.repository.next_competency_version_number(
                context, position.position_id
            ),
            criteria=tuple(
                EvaluationCriterion(
                    criterion_id=self.id_generator.new(),
                    company_id=position.company_id,
                    competency_model_version_id=version_id,
                    code=str(item["code"]),
                    name=str(item["name"]),
                    description=str(item["description"]),
                    weight=float(item["weight"]),
                    good_evidence=dict(item["good_evidence"]),
                    weak_evidence=dict(item["weak_evidence"]),
                    abstain_guidance=str(item["abstain_guidance"]),
                    common_questions=tuple(item.get("common_questions", ())),
                    required=bool(item["required"]),
                )
                for item in criteria
            ),
            prohibited_topics=tuple(prohibited_topics),
            interview_duration_minutes=interview_duration_minutes,
            persona_definition=persona_definition,
        )
        return self.repository.add_competency_model_version(context, version)

    def publish_version(
        self,
        context: TenantContext,
        *,
        version_id: str | OpaqueId,
        expected_version: int,
    ) -> CompetencyModelVersion:
        version = self.repository.get_competency_model_version(context, version_id)
        if version.row_version != expected_version:
            raise SafeApplicationError(
                ErrorCode.STALE_VERSION,
                current_version=version.row_version,
            )
        return self.repository.add_competency_model_version(
            context,
            version.publish(self.clock.now()),
        )


def criterion_version_snapshot(version: CompetencyModelVersion) -> dict[str, object]:
    if version.status.value not in {"published", "retired"}:
        raise SafeApplicationError(ErrorCode.CONFLICT)
    return {
        "company_id": str(version.company_id),
        "competency_model_version_id": str(version.competency_model_version_id),
        "position_id": str(version.position_id),
        "version_number": version.version_number,
        "status": version.status.value,
        "criteria": [criterion.to_view() for criterion in version.criteria],
    }
