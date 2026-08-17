from __future__ import annotations

import pytest
from interview_evidence.shared.config import RuntimeEnvironment, Settings
from pydantic import ValidationError


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": RuntimeEnvironment.TEST,
        "database_url": "postgresql://service:database-secret@example.invalid/app",
        "applicant_session_secret": "applicant-session-secret-value",
        "company_jwt_issuer": "https://identity.example.invalid/tenant",
        "company_jwt_audience": "interview-evidence-api",
        "company_jwks_url": "https://identity.example.invalid/tenant/jwks.json",
        "applicant_session_ttl_seconds": 1800,
        "invitation_public_base_url": "https://interview.example.invalid",
        "invitation_email_template": "applicant-invitation-v1",
        "default_retention_days": 180,
        "signed_url_ttl_seconds": 300,
        "event_queue_url": "https://sqs.ap-northeast-2.amazonaws.com/000000000000/events",
    }
    values.update(overrides)
    return Settings(**values)


def test_settings_are_typed_frozen_and_secret_safe() -> None:
    settings = _settings()

    rendered = repr(settings) + str(settings) + str(settings.safe_snapshot())
    assert "database-secret" not in rendered
    assert "applicant-session-secret-value" not in rendered
    assert rendered.count("[REDACTED]") >= 2
    assert settings.aws_region == "ap-northeast-2"

    with pytest.raises(ValidationError, match="frozen"):
        settings.aws_region = "us-east-1"  # type: ignore[misc]


def test_cross_region_model_use_requires_explicit_privacy_approval() -> None:
    with pytest.raises(ValidationError, match="cross-region"):
        _settings(bedrock_region="us-east-1")

    approved = _settings(
        bedrock_region="us-east-1",
        cross_region_model_approved=True,
    )
    assert approved.bedrock_region == "us-east-1"


def test_invalid_region_and_short_session_secret_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _settings(aws_region="not a region")
    with pytest.raises(ValidationError):
        _settings(applicant_session_secret="too-short")


def test_lane_runtime_inputs_use_the_documented_iep_environment_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "IEP_ENVIRONMENT": "dev",
        "IEP_DATABASE_URL": "postgresql://service:database-secret@example.invalid/app",
        "IEP_APPLICANT_SESSION_SECRET": "applicant-session-secret-value",
        "IEP_COMPANY_JWT_ISSUER": "https://identity.example.invalid/tenant",
        "IEP_COMPANY_JWT_AUDIENCE": "interview-evidence-api",
        "IEP_COMPANY_JWKS_URL": "https://identity.example.invalid/tenant/jwks.json",
        "IEP_APPLICANT_SESSION_TTL_SECONDS": "1800",
        "IEP_INVITATION_PUBLIC_BASE_URL": "https://interview.example.invalid",
        "IEP_INVITATION_EMAIL_TEMPLATE": "applicant-invitation-v1",
        "IEP_DEFAULT_RETENTION_DAYS": "180",
        "IEP_SIGNED_URL_TTL_SECONDS": "300",
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    settings = Settings(_env_file=None)

    assert settings.environment is RuntimeEnvironment.DEV
    assert settings.company_jwt_audience == "interview-evidence-api"
    assert settings.applicant_session_ttl_seconds == 1800
    assert settings.invitation_email_template == "applicant-invitation-v1"
    assert settings.default_retention_days == 180
    assert "database-secret" not in repr(settings)


@pytest.mark.parametrize(
    ("field_name", "unsafe_url"),
    (
        ("company_jwt_issuer", "https://admin:secret@identity.example.invalid/tenant"),
        ("company_jwks_url", "https://identity.example.invalid/jwks.json?token=raw-secret"),
        ("invitation_public_base_url", "https://interview.example.invalid/#raw-secret"),
    ),
)
def test_trusted_configuration_urls_reject_embedded_credentials_or_query_secrets(
    field_name: str,
    unsafe_url: str,
) -> None:
    with pytest.raises(ValidationError, match="userinfo, query, or fragment"):
        _settings(**{field_name: unsafe_url})
