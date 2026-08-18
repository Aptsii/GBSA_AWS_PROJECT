from __future__ import annotations

from datetime import UTC, datetime

import jwt
from interview_evidence.company_management.adapters.company_auth import JWTCompanyAuthenticator


class _SigningKey:
    key = "public-key"


class _JWKClient:
    def get_signing_key_from_jwt(self, credential: str) -> _SigningKey:
        assert credential == "company-id-token"
        return _SigningKey()


def test_cognito_identity_claims_create_company_principal(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    issued_at = datetime(2026, 8, 18, 9, tzinfo=UTC)
    expires_at = datetime(2026, 8, 18, 9, 15, tzinfo=UTC)

    def decode(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        return {
            "aud": "company-console-client",
            "cognito:groups": ["hiring_admin", "reviewer"],
            "custom:company_id": "0198a82a-0540-7000-8000-000000000001",
            "custom:company_user_id": "0198a82a-0540-7000-8000-000000000003",
            "email": "owner@example.test",
            "exp": int(expires_at.timestamp()),
            "iat": int(issued_at.timestamp()),
            "sub": "cognito-subject",
        }

    monkeypatch.setattr(jwt, "decode", decode)
    authenticator = JWTCompanyAuthenticator(
        issuer="https://identity.example.test/",
        audience="company-console-client",
        jwks_url="https://identity.example.test/.well-known/jwks.json",
    )
    authenticator._jwk_client = _JWKClient()  # type: ignore[attr-defined]

    principal = authenticator.authenticate("company-id-token")

    assert str(principal.company_id) == "0198a82a-0540-7000-8000-000000000001"
    assert str(principal.company_user_id) == "0198a82a-0540-7000-8000-000000000003"
    assert principal.identity_subject == "owner@example.test"
    assert principal.roles == frozenset({"hiring_admin", "reviewer"})
