from __future__ import annotations

from datetime import UTC, datetime

import jwt

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.security.principals import (
    CompanyAuthenticator,
    CompanyPrincipal,
)


class JWTCompanyAuthenticator:
    __slots__ = ("_audience", "_issuer", "_jwk_client")

    def __init__(self, *, issuer: str, audience: str, jwks_url: str) -> None:
        self._issuer = issuer.rstrip("/") + "/"
        self._audience = audience
        self._jwk_client = jwt.PyJWKClient(jwks_url)

    def authenticate(self, credential: str) -> CompanyPrincipal:
        try:
            signing_key = self._jwk_client.get_signing_key_from_jwt(credential)
            claims = jwt.decode(
                credential,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience=self._audience,
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "company_id", "company_user_id"]},
            )
            roles = claims.get("roles", [])
            if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
                raise ValueError("roles claim is invalid")
            return CompanyPrincipal(
                company_id=OpaqueId(str(claims["company_id"])),
                company_user_id=OpaqueId(str(claims["company_user_id"])),
                identity_subject=str(claims["sub"]),
                roles=frozenset(roles),
                issued_at=datetime.fromtimestamp(int(claims["iat"]), tz=UTC),
                expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
            )
        except (jwt.PyJWTError, KeyError, TypeError, ValueError):
            raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED) from None


def authenticate_company_bearer(
    authenticator: CompanyAuthenticator,
    authorization: str | None,
) -> CompanyPrincipal:
    if authorization is None:
        raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
    scheme, separator, credential = authorization.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not credential:
        raise SafeApplicationError(ErrorCode.AUTHENTICATION_REQUIRED)
    return authenticator.authenticate(credential)
