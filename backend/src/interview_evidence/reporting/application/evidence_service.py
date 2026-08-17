from __future__ import annotations

from interview_evidence.reporting.domain.report import Evidence, ReportItem


class EvidenceService:
    def validate_anchor(
        self,
        *,
        answer_turn_final: bool,
        answer_speaker: str,
        transcript_within_turn: bool,
        media_available: bool,
        technical_failure: bool,
    ) -> None:
        if not answer_turn_final or answer_speaker != "applicant":
            raise ValueError("Evidence requires a final applicant Turn")
        if not transcript_within_turn or not media_available or technical_failure:
            raise ValueError("Evidence anchor range is unavailable")

    def attach(self, item: ReportItem, evidence: Evidence, **anchor: bool | str) -> ReportItem:
        self.validate_anchor(**anchor)  # type: ignore[arg-type]
        return ReportItem(
            report_item_id=item.report_item_id,
            report_id=item.report_id,
            criterion_id=item.criterion_id,
            competency_model_version_id=item.competency_model_version_id,
            assessment_state=item.assessment_state,
            observation=item.observation,
            rationale=item.rationale,
            uncertainty=item.uncertainty,
            evidence=(*item.evidence, evidence),
            follow_up_question=item.follow_up_question,
        )
