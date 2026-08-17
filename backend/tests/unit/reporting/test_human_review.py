from __future__ import annotations

from interview_evidence.reporting.application.review_service import ReviewService
from interview_evidence.shared.tenant import TenantContext

from tests.fixtures.shared.factories import COMPANY_ID, REPORT_ID, make_tenant_context


def test_ai_original_is_immutable_and_human_reviews_are_append_only() -> None:
    service = ReviewService()
    context = TenantContext(**make_tenant_context())
    first = service.append(
        context,
        report_id=REPORT_ID,
        target_id="018f2000-0000-7000-8000-000000000251",
        review_type="assessment_override",
        value={"assessment_state": "needs_follow_up"},
        reason="근거 부족",
        idempotency_key="review-append-0001",
    )
    second = service.append(
        context,
        report_id=REPORT_ID,
        target_id="018f2000-0000-7000-8000-000000000251",
        review_type="note",
        value={"code": "follow_up"},
        reason=None,
        idempotency_key="review-append-0002",
    )
    assert first.company_id == COMPANY_ID
    assert service.history(context, REPORT_ID) == (first, second)
