from __future__ import annotations

from interview_evidence.shared.errors import ErrorCode, SafeApplicationError
from interview_evidence.shared.security.principals import (
    CompanyAuthenticator,
    CompanyPrincipal,
)


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
