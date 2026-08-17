from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interview_evidence.shared.audit import (
    AuditAppend,
    AuditResult,
    InMemoryAuditAppender,
)
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ActorType, TenantContext, TenantScopeViolation

NOW = datetime(2026, 8, 14, 12, 30, tzinfo=UTC)
COMPANY_ID = "0198a82a-0540-7000-8000-000000000001"
OTHER_COMPANY_ID = "0198a82a-0540-7000-8000-000000000002"


def _context(company_id: str = COMPANY_ID) -> TenantContext:
    return TenantContext(
        company_id=company_id,
        actor_type=ActorType.COMPANY_USER,
        actor_id="0198a82a-0540-7000-8000-000000000003",
        request_id="0198a82a-0540-7000-8000-000000000005",
        trace_id="trace-0001",
    )


def _appender() -> InMemoryAuditAppender:
    clock = FixedClock(NOW)
    return InMemoryAuditAppender(
        clock=clock,
        id_generator=UUID7Generator(clock, randbytes=lambda size: b"\x00" * size),
    )


@pytest.mark.asyncio
async def test_audit_append_derives_tenant_actor_and_trace_from_context() -> None:
    appender = _appender()
    command = AuditAppend(
        action="report.view",
        resource_type="report",
        resource_id="0198a82a-0540-7000-8000-000000000006",
        result=AuditResult.SUCCESS,
        metadata={"report_version": 1, "status": "ready"},
        idempotency_key="audit-operation-0001",
    )

    first = await appender.append(_context(), command)
    duplicate = await appender.append(_context(), command)

    assert first is duplicate
    assert first.company_id == COMPANY_ID
    assert first.actor_id == _context().actor_id
    assert first.request_id == _context().request_id
    assert first.trace_id == "trace-0001"
    assert len(await appender.list_for_tenant(_context())) == 1


@pytest.mark.asyncio
async def test_audit_metadata_rejects_source_text_tokens_and_urls() -> None:
    appender = _appender()

    for metadata in (
        {"answer_text": "지원자 답변 원문"},
        {"token": "secret-token"},
        {"locator": "https://signed.invalid/private"},
        {"note": "free form applicant content"},
        {"status": "RAWACCESSTOKEN1234567890ABCDEFG"},
    ):
        with pytest.raises(ValueError, match="audit metadata"):
            AuditAppend(
                action="report.view",
                resource_type="report",
                resource_id="0198a82a-0540-7000-8000-000000000006",
                result=AuditResult.DENIED,
                metadata=metadata,
                idempotency_key="audit-operation-0002",
            )

    assert await appender.list_for_tenant(_context()) == ()


def test_audit_result_values_match_the_frozen_public_receipt_contract() -> None:
    assert {result.value for result in AuditResult} == {"succeeded", "denied", "failed"}


@pytest.mark.asyncio
async def test_audit_reads_are_tenant_scoped() -> None:
    appender = _appender()
    event = await appender.append(
        _context(),
        AuditAppend(
            action="report.view",
            resource_type="report",
            resource_id="0198a82a-0540-7000-8000-000000000006",
            result=AuditResult.SUCCESS,
            metadata={},
            idempotency_key="audit-operation-0001",
        ),
    )

    with pytest.raises(TenantScopeViolation):
        await appender.get(_context(OTHER_COMPANY_ID), event.audit_event_id)
