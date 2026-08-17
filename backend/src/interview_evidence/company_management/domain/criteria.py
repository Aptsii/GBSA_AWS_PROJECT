from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from interview_evidence.shared._validation import utc_instant
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId

_CRITERION_CODE = re.compile(r"^[A-Z0-9_-]{2,40}$")


def _text(value: str, *, field_name: str, maximum: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{field_name} must contain between 1 and {maximum} characters")
    return normalized


class CompetencyModelStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class EvaluationCriterion:
    criterion_id: OpaqueId
    company_id: OpaqueId
    competency_model_version_id: OpaqueId
    code: str
    name: str
    description: str
    weight: float
    good_evidence: Mapping[str, Any]
    weak_evidence: Mapping[str, Any]
    abstain_guidance: str
    common_questions: tuple[str, ...]
    required: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "criterion_id", OpaqueId(self.criterion_id))
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(
            self,
            "competency_model_version_id",
            OpaqueId(self.competency_model_version_id),
        )
        if not _CRITERION_CODE.fullmatch(self.code):
            raise ValueError("criterion code must match the public contract")
        object.__setattr__(self, "name", _text(self.name, field_name="name", maximum=200))
        object.__setattr__(
            self,
            "description",
            _text(self.description, field_name="description", maximum=4_000),
        )
        if not math.isfinite(self.weight) or self.weight < 0:
            raise ValueError("criterion weight must be finite and non-negative")
        object.__setattr__(self, "good_evidence", MappingProxyType(dict(self.good_evidence)))
        object.__setattr__(self, "weak_evidence", MappingProxyType(dict(self.weak_evidence)))
        object.__setattr__(
            self,
            "abstain_guidance",
            _text(self.abstain_guidance, field_name="abstain_guidance", maximum=4_000),
        )
        object.__setattr__(
            self,
            "common_questions",
            tuple(question.strip() for question in self.common_questions if question.strip()),
        )

    def to_view(self) -> dict[str, object]:
        return {
            "criterion_id": str(self.criterion_id),
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "weight": self.weight,
            "good_evidence": dict(self.good_evidence),
            "weak_evidence": dict(self.weak_evidence),
            "abstain_guidance": self.abstain_guidance,
            "common_questions": list(self.common_questions),
            "required": self.required,
        }


@dataclass(frozen=True, slots=True)
class CompetencyModelVersion:
    competency_model_version_id: OpaqueId
    company_id: OpaqueId
    position_id: OpaqueId
    version_number: int
    criteria: tuple[EvaluationCriterion, ...]
    prohibited_topics: tuple[str, ...]
    interview_duration_minutes: int
    persona_definition: Mapping[str, Any]
    status: CompetencyModelStatus = CompetencyModelStatus.DRAFT
    published_at: datetime | None = None
    row_version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "competency_model_version_id",
            OpaqueId(self.competency_model_version_id),
        )
        object.__setattr__(self, "company_id", OpaqueId(self.company_id))
        object.__setattr__(self, "position_id", OpaqueId(self.position_id))
        if self.version_number < 1 or self.row_version < 1:
            raise ValueError("version numbers must be positive")
        object.__setattr__(self, "criteria", tuple(self.criteria))
        object.__setattr__(
            self,
            "prohibited_topics",
            tuple(topic.strip() for topic in self.prohibited_topics if topic.strip()),
        )
        if not 10 <= self.interview_duration_minutes <= 120:
            raise ValueError("interview duration must be between 10 and 120 minutes")
        object.__setattr__(
            self,
            "persona_definition",
            MappingProxyType(dict(self.persona_definition)),
        )
        if not isinstance(self.status, CompetencyModelStatus):
            object.__setattr__(self, "status", CompetencyModelStatus(self.status))
        if self.published_at is not None:
            object.__setattr__(self, "published_at", utc_instant(self.published_at))
        self._validate_criterion_scope()

    def _validate_criterion_scope(self) -> None:
        codes: set[str] = set()
        for criterion in self.criteria:
            if (
                criterion.company_id != self.company_id
                or criterion.competency_model_version_id != self.competency_model_version_id
            ):
                raise ValueError("criteria must belong to the same tenant and version")
            if criterion.code in codes:
                raise ValueError("criterion codes must be unique within a version")
            codes.add(criterion.code)

    def replace_criteria(
        self,
        criteria: tuple[EvaluationCriterion, ...],
    ) -> CompetencyModelVersion:
        if self.status is not CompetencyModelStatus.DRAFT:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return replace(self, criteria=tuple(criteria), row_version=self.row_version + 1)

    def publish(self, published_at: datetime) -> CompetencyModelVersion:
        if self.status is CompetencyModelStatus.PUBLISHED:
            return self
        if self.status is not CompetencyModelStatus.DRAFT or not self.criteria:
            raise SafeApplicationError(ErrorCode.CONFLICT)
        if not math.isclose(sum(item.weight for item in self.criteria), 1.0, abs_tol=1e-6):
            raise SafeApplicationError(ErrorCode.CONFLICT)
        return replace(
            self,
            status=CompetencyModelStatus.PUBLISHED,
            published_at=utc_instant(published_at),
            row_version=self.row_version + 1,
        )

    def to_view(self) -> dict[str, object]:
        return {
            "competency_model_version_id": str(self.competency_model_version_id),
            "position_id": str(self.position_id),
            "version_number": self.version_number,
            "criteria": [criterion.to_view() for criterion in self.criteria],
            "prohibited_topics": list(self.prohibited_topics),
            "interview_duration_minutes": self.interview_duration_minutes,
            "persona_definition": dict(self.persona_definition),
            "status": self.status.value,
            "row_version": self.row_version,
            "published_at": (
                self.published_at.isoformat().replace("+00:00", "Z")
                if self.published_at is not None
                else None
            ),
        }
