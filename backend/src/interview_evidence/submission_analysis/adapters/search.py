from __future__ import annotations

from dataclasses import dataclass, field

from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import ApplicantScope, TenantContext, ensure_applicant_scope
from interview_evidence.submission_analysis.domain.source import SourceReference


@dataclass(frozen=True, slots=True, repr=False)
class SearchRecord:
    scope: ApplicantScope
    reference: SourceReference
    text: str = field(repr=False)
    vector: tuple[float, ...]
    symbols: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.reference.company_id != self.scope.company_id:
            raise ValueError("search record reference must match applicant scope")
        if not self.vector:
            raise ValueError("search vectors cannot be empty")


class InMemorySubmissionSearch:
    __slots__ = ("_records",)

    def __init__(self) -> None:
        self._records: dict[tuple[OpaqueId, OpaqueId, OpaqueId, OpaqueId], SearchRecord] = {}

    def index(self, context: TenantContext, record: SearchRecord) -> None:
        ensure_applicant_scope(context, record.scope)
        key = (
            record.scope.company_id,
            record.scope.applicant_id,
            record.scope.invitation_id,
            record.reference.source_id,
        )
        self._records[key] = record

    def candidates(self, context: TenantContext, scope: ApplicantScope) -> tuple[SearchRecord, ...]:
        ensure_applicant_scope(context, scope)
        values = [
            record
            for (company_id, applicant_id, invitation_id, _), record in self._records.items()
            if company_id == scope.company_id
            and applicant_id == scope.applicant_id
            and invitation_id == scope.invitation_id
        ]
        values.sort(key=lambda item: str(item.reference.source_id))
        return tuple(values)

    def delete(self, context: TenantContext, scope: ApplicantScope, source_id: OpaqueId) -> bool:
        ensure_applicant_scope(context, scope)
        key = (scope.company_id, scope.applicant_id, scope.invitation_id, OpaqueId(source_id))
        self._records.pop(key, None)
        return key not in self._records
