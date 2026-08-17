from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
import pytest
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from fastapi.testclient import TestClient
from httpx import Response
from interview_evidence.main import (
    ProductionResources,
    create_app,
    create_application_routers,
    create_production_runtimes,
)
from interview_evidence.shared.aws_clients.ports import ObjectRef, ProtectedBytes
from interview_evidence.shared.aws_clients.s3 import S3ObjectStorage
from interview_evidence.shared.config import RuntimeEnvironment, Settings
from interview_evidence.shared.ids import SystemClock, UUID7Generator
from interview_evidence.shared.runtime import (
    DatabaseTransactionMiddleware,
    RequestSessionRegistry,
)
from interview_evidence.shared.security.principals import (
    CompanyPrincipal,
    FakeCompanyAuthenticator,
)
from pydantic import AnyHttpUrl, SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

DATABASE_URL = "postgresql+psycopg://interview:interview_local@localhost:5432/interview_evidence"
AWS_ENDPOINT_URL = "http://localhost:4566"
AWS_REGION = "ap-northeast-2"
BUCKET_NAME = "iep-local-contract-fixtures"
COMPANY_CREDENTIAL = "local-e2e-company-credential"


def _settings() -> Settings:
    return Settings(
        environment=RuntimeEnvironment.TEST,
        database_url=SecretStr(DATABASE_URL),
        applicant_session_secret=SecretStr("local-e2e-applicant-session-secret"),
        company_jwt_issuer=AnyHttpUrl("https://identity.local.invalid/"),
        company_jwt_audience="interview-evidence-api",
        company_jwks_url=AnyHttpUrl(
            "https://identity.local.invalid/.well-known/jwks.json"
        ),
        applicant_session_ttl_seconds=7_200,
        invitation_public_base_url=AnyHttpUrl("http://localhost:5174/"),
        invitation_email_template="invitation-v1",
        default_retention_days=30,
        signed_url_ttl_seconds=900,
        object_storage_bucket=BUCKET_NAME,
    )


def _local_s3() -> Any:
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        endpoint_url=AWS_ENDPOINT_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        config=Config(connect_timeout=1, read_timeout=2, retries={"max_attempts": 1}),
    )


def _require_local_services(engine: Engine, s3: Any) -> None:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        s3.head_bucket(Bucket=BUCKET_NAME)
    except (SQLAlchemyError, BotoCoreError, ClientError, OSError) as error:
        pytest.skip(f"local Compose services are unavailable: {type(error).__name__}")


def _assert_response(response: Response, expected_status: int) -> dict[str, object]:
    assert response.status_code == expected_status, response.text
    result = response.json()
    assert isinstance(result, dict)
    return result


def _company_headers(seed: str, *, version: int | None = None) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {COMPANY_CREDENTIAL}",
        "Idempotency-Key": f"e2e-{seed}-{uuid4()}",
    }
    if version is not None:
        headers["If-Match-Version"] = str(version)
    return headers


def _applicant_headers(seed: str) -> dict[str, str]:
    return {"Idempotency-Key": f"e2e-{seed}-{uuid4()}"}


def test_company_to_human_decision_uses_production_runtime_and_local_services(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_ENDPOINT_URL", AWS_ENDPOINT_URL)
    settings = _settings()
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    s3 = _local_s3()
    _require_local_services(engine, s3)

    ids = UUID7Generator()
    now = datetime.now(UTC)
    company_id = ids.new()
    company_user_id = ids.new()
    authenticator = FakeCompanyAuthenticator(SystemClock())
    authenticator.register(
        COMPANY_CREDENTIAL,
        CompanyPrincipal(
            company_id=company_id,
            company_user_id=company_user_id,
            identity_subject="local-e2e-company-user",
            roles=frozenset({"hiring_admin", "reviewer"}),
            issued_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=1),
        ),
    )
    storage = S3ObjectStorage(s3, bucket=BUCKET_NAME)
    resources = ProductionResources(
        settings=settings,
        engine=engine,
        sessions=RequestSessionRegistry(engine),
        object_storage=storage,
    )
    runtimes = create_production_runtimes(
        resources,
        company_authenticator=authenticator,
    )
    app = create_app(create_application_routers(runtimes))
    app.add_middleware(DatabaseTransactionMiddleware, registry=resources.sessions)

    try:
        with TestClient(app) as client:
            position = _assert_response(
                client.post(
                    "/v1/positions",
                    headers=_company_headers("position"),
                    json={
                        "title": "플랫폼 백엔드 엔지니어",
                        "description": "테넌트 격리와 복구 가능한 비동기 처리를 설계합니다.",
                    },
                ),
                201,
            )
            position_id = str(position["position_id"])

            criterion_version = _assert_response(
                client.post(
                    f"/v1/positions/{position_id}/competency-model-versions",
                    headers=_company_headers("criterion-create"),
                    json={
                        "criteria": [
                            {
                                "code": "SYSTEM_DESIGN",
                                "name": "시스템 설계",
                                "description": "경계와 복구 트레이드오프를 설명합니다.",
                                "weight": 1,
                                "good_evidence": {"signals": ["tradeoff", "recovery"]},
                                "weak_evidence": {"signals": ["generic"]},
                                "abstain_guidance": "최종 답변 근거가 부족하면 유보합니다.",
                                "common_questions": ["최근 복구 설계 판단을 설명해 주세요."],
                                "required": True,
                            }
                        ],
                        "prohibited_topics": ["가족관계"],
                        "interview_duration_minutes": 30,
                        "persona_definition": {"name": "하루", "tone": "professional"},
                    },
                ),
                201,
            )
            criterion_version_id = str(
                criterion_version["competency_model_version_id"]
            )
            published_version = _assert_response(
                client.post(
                    f"/v1/competency-model-versions/{criterion_version_id}/publish",
                    headers=_company_headers("criterion-publish", version=1),
                ),
                200,
            )

            campaign = _assert_response(
                client.post(
                    "/v1/campaigns",
                    headers=_company_headers("campaign-create"),
                    json={
                        "position_id": position_id,
                        "competency_model_version_id": criterion_version_id,
                        "name": "2026 플랫폼 채용",
                        "candidate_instructions": "동의 후 제출 자료와 면접을 진행합니다.",
                    },
                ),
                201,
            )
            campaign_id = str(campaign["campaign_id"])
            _assert_response(
                client.post(
                    f"/v1/campaigns/{campaign_id}/publish",
                    headers=_company_headers("campaign-publish", version=1),
                ),
                200,
            )
            invitations = _assert_response(
                client.post(
                    f"/v1/campaigns/{campaign_id}/invitations",
                    headers=_company_headers("invitation"),
                    json={
                        "applicants": [
                            {
                                "email": "local-e2e-candidate@example.invalid",
                                "display_name": "지원자",
                            }
                        ],
                        "expires_at": (now + timedelta(days=1)).isoformat(),
                    },
                ),
                202,
            )
            invitation_values = invitations["invitations"]
            assert isinstance(invitation_values, list) and invitation_values
            invitation = invitation_values[0]
            assert isinstance(invitation, dict)
            invitation_id = str(invitation["invitation_id"])
            raw_invitation_token = (
                runtimes.company.hiring_service.get_test_delivery_token(invitation_id)
            )

            exchange = client.post(
                "/v1/applicant/access/exchange",
                headers=_applicant_headers("access-exchange"),
                json={"invitation_token": raw_invitation_token},
            )
            assert exchange.status_code == 204, exchange.text
            session_cookie = client.cookies.get("iep_applicant_session")
            assert session_cookie is not None

            identity = _assert_response(
                client.post(
                    "/v1/applicant/identity-verifications",
                    headers=_applicant_headers("identity"),
                    json={
                        "display_name": "지원자",
                        "verification_value": "verified-by-invitation-link",
                    },
                ),
                200,
            )
            consent = _assert_response(
                client.post(
                    "/v1/applicant/consents",
                    headers=_applicant_headers("consent"),
                    json={
                        "policy_version": "local-e2e-v1",
                        "accepted_purposes": [
                            "document_analysis",
                            "recording",
                            "ai_assessment",
                        ],
                        "consent_content_digest": hashlib.sha256(
                            b"local-e2e-consent-v1"
                        ).hexdigest(),
                    },
                ),
                201,
            )

            submission = _assert_response(
                client.post(
                    "/v1/applicant/submissions",
                    headers=_applicant_headers("submission"),
                    json={
                        "source_type": "public_git",
                        "public_url": "https://github.com/octocat/Hello-World",
                        "candidate_identity_inputs": {"claimed_owner": "octocat"},
                    },
                ),
                202,
            )
            equipment = _assert_response(
                client.post(
                    "/v1/applicant/equipment-checks",
                    headers=_applicant_headers("equipment"),
                    json={
                        "camera": {"status": "ready"},
                        "microphone": {"status": "ready"},
                        "network": {"status": "ready"},
                    },
                ),
                201,
            )
            strategy_id = ids.new()
            interview = _assert_response(
                client.post(
                    "/v1/applicant/interview-sessions",
                    headers=_applicant_headers("interview"),
                    json={
                        "equipment_check_id": equipment["equipment_check_id"],
                        "strategy_id": str(strategy_id),
                        "acknowledged_partial_analysis": True,
                    },
                ),
                201,
            )
            session_id = str(interview["interview_session_id"])

            session_adapter = runtimes.company_applicant.session_adapter
            assert session_adapter is not None
            applicant_principal = session_adapter.authenticate(session_cookie)
            applicant_context = applicant_principal.to_tenant_context(
                request_id=str(ids.new()),
                trace_id="local-e2e-object-storage",
            )
            applicant_scope = applicant_principal.applicant_scope()
            artifact = ObjectRef(
                company_id=applicant_scope.company_id,
                applicant_scope=applicant_scope,
                object_id=ids.new(),
            )
            artifact_content = ProtectedBytes(b"local-e2e-contract-artifact")
            asyncio.run(
                storage.put(
                    applicant_context,
                    artifact,
                    artifact_content,
                    media_type="application/octet-stream",
                )
            )
            restored = asyncio.run(storage.get(applicant_context, artifact))

            decision = _assert_response(
                client.post(
                    f"/v1/invitations/{invitation_id}/final-decisions",
                    headers=_company_headers("final-decision"),
                    json={
                        "decision": "hold",
                        "reason": "회사 담당자가 실제 면접 결과를 추가 검토합니다.",
                    },
                ),
                201,
            )

            persisted_positions = _assert_response(
                client.get(
                    "/v1/positions",
                    headers={"Authorization": f"Bearer {COMPANY_CREDENTIAL}"},
                ),
                200,
            )
            persisted_submissions = client.get("/v1/applicant/submissions")
            assert persisted_submissions.status_code == 200, persisted_submissions.text
            resume = _assert_response(
                client.get(f"/v1/applicant/interview-sessions/{session_id}/resume"),
                200,
            )

            assert published_version["status"] == "published"
            assert identity["state"] == "identity_verified"
            accepted_purposes = consent["accepted_purposes"]
            assert isinstance(accepted_purposes, list)
            assert {str(value) for value in accepted_purposes} == {
                "document_analysis",
                "recording",
                "ai_assessment",
            }
            assert submission["status"] == "received"
            assert equipment["overall_status"] == "ready"
            assert interview["state"] == "preparing"
            assert restored.reveal() == artifact_content.reveal()
            assert decision["review_type"] == "final_decision"
            assert decision["created_by"] == str(company_user_id)
            position_items = persisted_positions["items"]
            assert isinstance(position_items, list)
            assert any(
                isinstance(item, dict) and item.get("position_id") == position_id
                for item in position_items
            )
            submission_items = persisted_submissions.json()
            assert isinstance(submission_items, list)
            assert any(
                isinstance(item, dict)
                and item.get("submission_id") == submission["submission_id"]
                for item in submission_items
            )
            assert resume["interview_session_id"] == session_id

            deletion = asyncio.run(storage.delete(applicant_context, artifact))
            assert deletion.verified_absent is True
    finally:
        engine.dispose()
