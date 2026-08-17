from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from interview_evidence.reporting.domain.report import AssessmentState, Evidence, ReportItem

from tests.fixtures.shared.factories import COMPANY_ID, CRITERION_ID, MODEL_ID, REPORT_ID


def _evidence() -> Evidence:
    return Evidence(
        evidence_id="018f2000-0000-7000-8000-000000000250",
        company_id=COMPANY_ID,
        report_item_id="018f2000-0000-7000-8000-000000000251",
        criterion_id=CRITERION_ID,
        competency_model_version_id=MODEL_ID,
        answer_turn_id="018f2000-0000-7000-8000-000000000252",
        transcript_segment_id="018f2000-0000-7000-8000-000000000253",
        video_start_ms=1000,
        video_end_ms=3000,
        observation="복구 절차를 설명함",
        rationale="구체적 순서를 제시함",
        sufficiency="direct",
        generation_version="report-v1",
        created_at=datetime(2026, 8, 17, tzinfo=UTC),
    )


def test_confirmed_item_requires_valid_evidence_and_range() -> None:
    with pytest.raises(ValueError, match="Evidence"):
        ReportItem(
            report_item_id="018f2000-0000-7000-8000-000000000251",
            report_id=REPORT_ID,
            criterion_id=CRITERION_ID,
            competency_model_version_id=MODEL_ID,
            assessment_state=AssessmentState.CONFIRMED,
            observation="관찰",
            rationale="근거",
            uncertainty="낮음",
        )
    assert ReportItem(
        report_item_id="018f2000-0000-7000-8000-000000000251",
        report_id=REPORT_ID,
        criterion_id=CRITERION_ID,
        competency_model_version_id=MODEL_ID,
        assessment_state=AssessmentState.CONFIRMED,
        observation="관찰",
        rationale="근거",
        uncertainty="낮음",
        evidence=(_evidence(),),
    ).evidence
    with pytest.raises(ValueError, match="range"):
        replace(_evidence(), video_end_ms=500)
