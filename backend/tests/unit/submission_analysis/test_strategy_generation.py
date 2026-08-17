from __future__ import annotations

from datetime import UTC, datetime

import pytest
from interview_evidence.shared.ids import FixedClock, UUID7Generator
from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.submission_analysis.application.strategy_service import StrategyService
from interview_evidence.submission_analysis.domain.source import SourceLocation, SourceReference

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    MODEL_ID,
    make_criterion_snapshot,
    make_tenant_context,
)


def _context() -> TenantContext:
    return TenantContext(**make_tenant_context())


def _scope() -> ApplicantScope:
    return ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)


def _id_generator(clock: FixedClock, value: int) -> UUID7Generator:
    return UUID7Generator(clock, randbytes=lambda size: bytes([value]) * size)


def test_strategy_generation_keeps_fixed_criteria_and_source_provenance() -> None:
    clock = FixedClock(datetime(2026, 8, 17, tzinfo=UTC))
    service = StrategyService(
        clock=clock,
        id_generator=_id_generator(clock, 44),
    )
    source = SourceReference(
        company_id=COMPANY_ID,
        source_type="submission_chunk",
        source_id="018f2000-0000-7000-8000-000000000341",
        source_version=1,
        source_location=SourceLocation(page=2, section="프로젝트", start_offset=0),
        source_hash="c" * 64,
    )

    strategy = service.generate(
        _context(),
        scope=_scope(),
        criterion_snapshot=make_criterion_snapshot(),
        verification_points=(
            {
                "criterion_id": make_criterion_snapshot()["criteria"][0]["criterion_id"],
                "prompt": "장애 복구를 확인",
            },
        ),
        source_references=(source,),
        duration_minutes=30,
        model_config_version="strategy-v1",
        partial=False,
    )

    assert strategy.competency_model_version_id == MODEL_ID
    assert (
        strategy.common_topics[0]["criterion_id"]
        == make_criterion_snapshot()["criteria"][0]["criterion_id"]
    )
    assert strategy.source_reference_candidates[0].source_id == source.source_id
    assert strategy.status == "ready"


def test_strategy_rejects_verification_point_outside_fixed_criteria() -> None:
    clock = FixedClock(datetime(2026, 8, 17, tzinfo=UTC))
    service = StrategyService(
        clock=clock,
        id_generator=_id_generator(clock, 45),
    )
    with pytest.raises(ValueError, match="fixed criterion"):
        service.generate(
            _context(),
            scope=_scope(),
            criterion_snapshot=make_criterion_snapshot(),
            verification_points=(
                {"criterion_id": "018f2000-0000-7000-8000-000000000999", "prompt": "invalid"},
            ),
            source_references=(),
            duration_minutes=30,
            model_config_version="strategy-v1",
            partial=True,
        )
