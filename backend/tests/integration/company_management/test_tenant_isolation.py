from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from interview_evidence.company_management.api.company_routes import (
    CompanyRouteRuntime,
    create_company_router,
)
from interview_evidence.company_management.application.company_service import CompanyService
from interview_evidence.company_management.application.criteria_service import CriteriaService
from interview_evidence.company_management.application.hiring_service import HiringService
from interview_evidence.company_management.domain.company import Position
from interview_evidence.company_management.repositories.postgres import (
    CompanyManagementRepository,
    register_company_models,
)
from interview_evidence.main import create_app
from interview_evidence.shared.database import metadata
from interview_evidence.shared.ids import FixedClock, OpaqueId, UUID7Generator
from interview_evidence.shared.security.principals import (
    CompanyPrincipal,
    FakeCompanyAuthenticator,
)
from interview_evidence.shared.tenant import (
    ActorType,
    TenantContext,
    TenantScopeViolation,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000001")
OTHER_COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000002")
POSITION_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000003")


def _context(company_id: OpaqueId) -> TenantContext:
    return TenantContext(
        company_id=company_id,
        actor_type=ActorType.COMPANY_USER,
        actor_id=OpaqueId("0198b6c5-8800-7000-8000-000000000004"),
        request_id=OpaqueId("0198b6c5-8800-7000-8000-000000000005"),
        trace_id="trace-tenant-isolation",
    )


def test_repository_requires_matching_tenant_for_every_read_and_write() -> None:
    register_company_models()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    try:
        with Session(engine) as session:
            repository = CompanyManagementRepository(session)
            position = Position(
                position_id=OpaqueId(POSITION_ID),
                company_id=OpaqueId(COMPANY_ID),
                title="백엔드 엔지니어",
                description="분산 시스템을 설계합니다.",
                created_by=OpaqueId("0198b6c5-8800-7000-8000-000000000004"),
                created_at=NOW,
            )
            repository.add_position(_context(COMPANY_ID), position)

            with pytest.raises(TenantScopeViolation):
                repository.get_position(_context(OTHER_COMPANY_ID), POSITION_ID)
            with pytest.raises(TenantScopeViolation):
                repository.add_position(_context(OTHER_COMPANY_ID), position)
    finally:
        metadata.drop_all(engine)
        engine.dispose()


def test_routes_hide_tenant_lists_and_deny_foreign_resource_ids() -> None:
    register_company_models()
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    try:
        repository = CompanyManagementRepository(session)
        clock = FixedClock(NOW)
        ids = UUID7Generator(clock)
        company_service = CompanyService(repository, clock=clock, id_generator=ids)
        criteria_service = CriteriaService(repository, clock=clock, id_generator=ids)
        hiring_service = HiringService(repository, clock=clock, id_generator=ids)
        owned = company_service.create_position(
            _context(COMPANY_ID),
            title="백엔드 엔지니어",
            description="테넌트 A의 직무입니다.",
        )
        authenticator = FakeCompanyAuthenticator(clock)
        authenticator.register(
            "tenant-b-token",
            CompanyPrincipal(
                company_id=OTHER_COMPANY_ID,
                company_user_id=OpaqueId("0198b6c5-8800-7000-8000-000000000014"),
                identity_subject="tenant-b-user",
                roles=frozenset({"hiring_admin"}),
                issued_at=NOW,
                expires_at=NOW.replace(hour=10),
            ),
        )
        client = TestClient(
            create_app(
                routers=(
                    create_company_router(
                        CompanyRouteRuntime(
                            authenticator=authenticator,
                            company_service=company_service,
                            criteria_service=criteria_service,
                            hiring_service=hiring_service,
                        )
                    ),
                )
            )
        )
        headers = {"Authorization": "Bearer tenant-b-token"}

        assert client.get("/v1/positions", headers=headers).json()["items"] == []
        denied = client.post(
            f"/v1/positions/{owned.position_id}/competency-model-versions",
            headers={**headers, "Idempotency-Key": "cross-tenant-denied-0001"},
            json={
                "criteria": [
                    {
                        "code": "BACKEND_DESIGN",
                        "name": "백엔드 설계",
                        "description": "설계 판단을 설명합니다.",
                        "weight": 1,
                        "good_evidence": {},
                        "weak_evidence": {},
                        "abstain_guidance": "근거가 없으면 유보합니다.",
                        "common_questions": [],
                        "required": True,
                    }
                ],
                "prohibited_topics": [],
                "interview_duration_minutes": 40,
                "persona_definition": {"name": "하루"},
            },
        )
        assert denied.status_code == 403
        assert denied.json()["code"] == "TENANT_SCOPE_DENIED"
    finally:
        session.close()
        metadata.drop_all(engine)
        engine.dispose()
