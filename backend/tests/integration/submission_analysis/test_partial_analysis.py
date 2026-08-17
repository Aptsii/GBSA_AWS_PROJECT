from __future__ import annotations

import pytest
from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.workers.analysis.handlers import (
    AnalysisJob,
    AnalysisJobHandler,
    AnalysisOutcome,
)

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_tenant_context,
)


def _context() -> TenantContext:
    return TenantContext(**make_tenant_context())


def _job(key: str = "analysis-job-key-0001") -> AnalysisJob:
    return AnalysisJob(
        company_id=COMPANY_ID,
        scope=ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID),
        submission_id="018f2000-0000-7000-8000-000000000351",
        analysis_version=1,
        source_type="pdf",
        idempotency_key=key,
    )


def test_partial_analysis_is_successful_and_replayed_idempotently() -> None:
    handler = AnalysisJobHandler(max_attempts=3)
    calls = 0

    def process(_job: AnalysisJob) -> AnalysisOutcome:
        nonlocal calls
        calls += 1
        return AnalysisOutcome(status="partial", impact_code="ONE_PAGE_UNREADABLE")

    first = handler.handle(_context(), _job(), process)
    replay = handler.handle(_context(), _job(), process)

    assert first == replay
    assert first.status == "partial"
    assert calls == 1
    events = handler.pending_events(_context())
    assert len(events) == 1
    assert events[0].event_type == "submission.analysis_completed"
    assert set(events[0].payload) == {
        "invitation_id",
        "submission_id",
        "analysis_id",
        "status",
        "impact_code",
    }


def test_retryable_failure_moves_to_dlq_after_bounded_attempts() -> None:
    handler = AnalysisJobHandler(max_attempts=2)

    def unavailable(_job: AnalysisJob) -> AnalysisOutcome:
        raise SafeApplicationError(ErrorCode.DEPENDENCY_UNAVAILABLE)

    with pytest.raises(SafeApplicationError):
        handler.handle(_context(), _job("analysis-job-key-0002"), unavailable)
    result = handler.handle(_context(), _job("analysis-job-key-0002"), unavailable)

    assert result.status == "failed"
    assert result.impact_code == "DLQ_DEPENDENCY_UNAVAILABLE"
    assert handler.dlq_count == 1


def test_non_retryable_failure_is_not_retried() -> None:
    handler = AnalysisJobHandler(max_attempts=3)

    def invalid(_job: AnalysisJob) -> AnalysisOutcome:
        raise SafeApplicationError(ErrorCode.INVALID_REQUEST)

    result = handler.handle(_context(), _job("analysis-job-key-0003"), invalid)

    assert result.status == "failed"
    assert result.impact_code == "INVALID_REQUEST"
    assert handler.attempts_for(_job("analysis-job-key-0003")) == 1
