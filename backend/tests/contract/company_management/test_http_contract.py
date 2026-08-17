from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from interview_evidence.company_management.api.applicant_routes import (
    ApplicantRouteRuntime,
    create_applicant_router,
)
from interview_evidence.company_management.api.company_routes import (
    CompanyRouteRuntime,
    create_company_router,
)
from interview_evidence.company_management.application.applicant_access_service import (
    ApplicantAccessService,
)
from interview_evidence.company_management.application.company_service import CompanyService
from interview_evidence.company_management.application.criteria_service import CriteriaService
from interview_evidence.company_management.application.hiring_service import HiringService
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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

NOW = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
COMPANY_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000001")
COMPANY_USER_ID = OpaqueId("0198b6c5-8800-7000-8000-000000000002")
COMPANY_TOKEN = "company-bearer-token-for-contract-tests"


def test_company_and_applicant_http_routes_match_the_frozen_contract() -> None:
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
        company_auth = FakeCompanyAuthenticator(clock)
        company_auth.register(
            COMPANY_TOKEN,
            CompanyPrincipal(
                company_id=COMPANY_ID,
                company_user_id=COMPANY_USER_ID,
                identity_subject="company-user-subject",
                roles=frozenset({"hiring_admin"}),
                issued_at=NOW,
                expires_at=NOW.replace(hour=10),
            ),
        )
        company_service = CompanyService(repository, clock=clock, id_generator=ids)
        criteria_service = CriteriaService(repository, clock=clock, id_generator=ids)
        hiring_service = HiringService(repository, clock=clock, id_generator=ids)
        applicant_service = ApplicantAccessService(repository, clock=clock, id_generator=ids)
        company_runtime = CompanyRouteRuntime(
            authenticator=company_auth,
            company_service=company_service,
            criteria_service=criteria_service,
            hiring_service=hiring_service,
        )
        applicant_runtime = ApplicantRouteRuntime(
            access_service=applicant_service,
            hiring_service=hiring_service,
        )
        client = TestClient(
            create_app(
                routers=(
                    create_company_router(company_runtime),
                    create_applicant_router(applicant_runtime),
                )
            )
        )
        headers = {"Authorization": f"Bearer {COMPANY_TOKEN}"}

        me = client.get("/v1/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["company_id"] == str(COMPANY_ID)

        position = client.post(
            "/v1/positions",
            headers={**headers, "Idempotency-Key": "create-position-0001"},
            json={"title": "백엔드 엔지니어", "description": "서비스를 설계합니다."},
        )
        assert position.status_code == 201
        position_id = position.json()["position_id"]
        assert (
            client.get("/v1/positions", headers=headers).json()["items"][0]["position_id"]
            == position_id
        )

        version = client.post(
            f"/v1/positions/{position_id}/competency-model-versions",
            headers={**headers, "Idempotency-Key": "create-criterion-version-0001"},
            json={
                "criteria": [
                    {
                        "code": "BACKEND_DESIGN",
                        "name": "백엔드 설계",
                        "description": "설계 판단을 설명합니다.",
                        "weight": 1,
                        "good_evidence": {"signals": ["tradeoff"]},
                        "weak_evidence": {"signals": ["generic"]},
                        "abstain_guidance": "근거가 없으면 유보합니다.",
                        "common_questions": ["설계 사례를 설명해 주세요."],
                        "required": True,
                    }
                ],
                "prohibited_topics": ["가족관계"],
                "interview_duration_minutes": 40,
                "persona_definition": {"name": "하루", "tone": "professional"},
            },
        )
        assert version.status_code == 201
        version_id = version.json()["competency_model_version_id"]
        published_version = client.post(
            f"/v1/competency-model-versions/{version_id}/publish",
            headers={
                **headers,
                "Idempotency-Key": "publish-criterion-version-0001",
                "If-Match-Version": "1",
            },
        )
        assert published_version.status_code == 200
        assert published_version.json()["status"] == "published"

        campaign = client.post(
            "/v1/campaigns",
            headers={**headers, "Idempotency-Key": "create-campaign-0001"},
            json={
                "position_id": position_id,
                "competency_model_version_id": version_id,
                "name": "2026 백엔드 채용",
                "candidate_instructions": "안내를 확인해 주세요.",
            },
        )
        assert campaign.status_code == 201
        campaign_id = campaign.json()["campaign_id"]
        assert (
            client.post(
                f"/v1/campaigns/{campaign_id}/publish",
                headers={
                    **headers,
                    "Idempotency-Key": "publish-campaign-0001",
                    "If-Match-Version": "1",
                },
            ).status_code
            == 200
        )

        invitations = client.post(
            f"/v1/campaigns/{campaign_id}/invitations",
            headers={**headers, "Idempotency-Key": "issue-invitations-0001"},
            json={
                "applicants": [{"email": "candidate@example.com", "display_name": "지원자"}],
                "expires_at": "2026-08-24T09:00:00Z",
            },
        )
        assert invitations.status_code == 202
        invitation_id = invitations.json()["invitations"][0]["invitation_id"]
        assert (
            client.get(f"/v1/campaigns/{campaign_id}/invitations", headers=headers).json()["items"][
                0
            ]["invitation_id"]
            == invitation_id
        )

        raw_token = hiring_service.get_test_delivery_token(invitation_id)
        exchange = client.post(
            "/v1/applicant/access/exchange",
            headers={"Idempotency-Key": "exchange-invitation-0001"},
            json={"invitation_token": raw_token},
        )
        assert exchange.status_code == 204
        assert "HttpOnly" in exchange.headers["set-cookie"]

        identity = client.post(
            "/v1/applicant/identity-verifications",
            headers={"Idempotency-Key": "verify-identity-0001"},
            json={"display_name": "지원자", "verification_value": "email-link-proof"},
        )
        assert identity.status_code == 200
        assert identity.json()["state"] == "identity_verified"

        consent = client.post(
            "/v1/applicant/consents",
            headers={"Idempotency-Key": "record-consent-0001"},
            json={
                "policy_version": "consent-v1",
                "accepted_purposes": [
                    "document_analysis",
                    "recording",
                    "ai_assessment",
                ],
                "consent_content_digest": "a" * 64,
            },
        )
        assert consent.status_code == 201
        assert consent.json()["accepted_purposes"] == [
            "ai_assessment",
            "document_analysis",
            "recording",
        ]
    finally:
        session.close()
        metadata.drop_all(engine)
        engine.dispose()
