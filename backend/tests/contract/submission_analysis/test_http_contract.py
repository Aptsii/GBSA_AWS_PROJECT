from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from interview_evidence.shared.tenant import ApplicantScope, TenantContext
from interview_evidence.submission_analysis.api.applicant_routes import (
    ApplicantRouteRuntime,
    create_applicant_router,
)
from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    make_tenant_context,
)


class _SubmissionServiceStub:
    def create_upload_intent(self, **_: Any) -> dict[str, object]:
        return {
            "upload_id": "018f2000-0000-7000-8000-000000000301",
            "method": "PUT",
            "url": "https://uploads.invalid/opaque",
            "required_headers": {"content-type": "application/pdf"},
            "expires_at": datetime(2026, 8, 17, 1, tzinfo=UTC),
        }

    def register_submission(self, **_: Any) -> dict[str, object]:
        return {
            "submission_id": "018f2000-0000-7000-8000-000000000302",
            "source_type": "public_git",
            "status": "received",
            "failure_code": None,
            "impact_summary": None,
            "created_at": datetime(2026, 8, 17, tzinfo=UTC),
        }

    def list_submissions(self, **_: Any) -> list[dict[str, object]]:
        return [self.register_submission()]

    def get_readiness(self, **_: Any) -> dict[str, object]:
        return {
            "overall_status": "analyzing",
            "submissions": self.list_submissions(),
            "interview_ready": False,
            "strategy_id": None,
            "strategy_version": None,
            "impact_summary": None,
        }


def _context() -> TenantContext:
    return TenantContext(**make_tenant_context())


def _client() -> TestClient:
    runtime = ApplicantRouteRuntime(
        service=_SubmissionServiceStub(),
        scope_provider=lambda _request: (
            _context(),
            ApplicantScope(
                company_id=COMPANY_ID,
                applicant_id=APPLICANT_ID,
                invitation_id=INVITATION_ID,
            ),
        ),
    )
    app = FastAPI()
    app.include_router(create_applicant_router(runtime), prefix="/v1")
    return TestClient(app)


def test_submission_routes_match_the_frozen_http_contract() -> None:
    with _client() as client:
        upload = client.post(
            "/v1/applicant/submissions/upload-intents",
            headers={"Idempotency-Key": "submission-upload-0001"},
            json={
                "source_type": "pdf",
                "filename": "portfolio.pdf",
                "media_type": "application/pdf",
                "byte_size": 1024,
                "sha256": "a" * 64,
            },
        )
        assert upload.status_code == 201
        assert set(upload.json()) == {
            "upload_id",
            "method",
            "url",
            "required_headers",
            "expires_at",
        }

        submission = client.post(
            "/v1/applicant/submissions",
            headers={"Idempotency-Key": "submission-register-0001"},
            json={
                "source_type": "public_git",
                "public_url": "https://github.com/example/public-repo",
                "candidate_identity_inputs": {"login": "candidate"},
            },
        )
        assert submission.status_code == 202
        assert submission.json()["status"] == "received"

        assert client.get("/v1/applicant/submissions").status_code == 200
        readiness = client.get("/v1/applicant/analysis-status")
        assert readiness.status_code == 200
        assert readiness.json()["interview_ready"] is False


def test_submission_contract_rejects_untrusted_company_and_unknown_fields() -> None:
    with _client() as client:
        response = client.post(
            "/v1/applicant/submissions",
            headers={"Idempotency-Key": "submission-register-0002"},
            json={
                "source_type": "public_url",
                "public_url": "https://example.com/portfolio",
                "company_id": COMPANY_ID,
            },
        )
        assert response.status_code == 422
