from __future__ import annotations

from datetime import UTC, datetime

from interview_evidence.reporting.domain.report import AssessmentState, Report, ReportItem
from interview_evidence.shared.ids import OpaqueId, UUID7Generator


class ReportGenerator:
    def __init__(self) -> None:
        self._ids = UUID7Generator()

    def generate(
        self,
        *,
        company_id: str | OpaqueId,
        session_id: str | OpaqueId,
        model_id: str | OpaqueId,
        criteria: tuple[tuple[str, str], ...],
        evidence_by_criterion: dict[str, tuple[object, ...]],
    ) -> Report:
        report_id = self._ids.new()
        items = tuple(
            ReportItem(
                self._ids.new(),
                report_id,
                OpaqueId(criterion_id),
                OpaqueId(model_id),
                AssessmentState.NEEDS_FOLLOW_UP
                if not evidence_by_criterion.get(criterion_id)
                else AssessmentState.CONFIRMED,
                f"{name} 관찰",
                "제공된 Evidence 기준",
                "Evidence 범위에 한정",
                tuple(evidence_by_criterion.get(criterion_id, ())),
                None if evidence_by_criterion.get(criterion_id) else "추가 사례를 확인하세요.",
            )
            for criterion_id, name in criteria
        )
        return Report(
            report_id,
            OpaqueId(company_id),
            OpaqueId(session_id),
            OpaqueId(model_id),
            1,
            "ready",
            "Evidence 기반 AI 원본",
            "report-v1",
            "prompt-v1",
            items,
            datetime.now(UTC),
        )
