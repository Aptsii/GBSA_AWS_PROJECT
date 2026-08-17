"""Typed runtime configuration with redacted string and mapping projections."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Final

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_AWS_REGION: Final = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
_REDACTED: Final = "[REDACTED]"


class RuntimeEnvironment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"


class Settings(BaseSettings):
    """Application settings whose secrets cannot leak through normal rendering."""

    model_config = SettingsConfigDict(
        env_prefix="IEP_",
        env_nested_delimiter="__",
        frozen=True,
        extra="forbid",
    )

    environment: RuntimeEnvironment = RuntimeEnvironment.LOCAL
    service_name: str = Field(default="interview-evidence", pattern=r"^[a-z0-9-]{3,64}$")
    aws_region: str = "ap-northeast-2"
    bedrock_region: str = "ap-northeast-2"
    cross_region_model_approved: bool = False
    database_url: SecretStr
    applicant_session_secret: SecretStr = Field(min_length=16)
    company_jwt_issuer: AnyHttpUrl
    company_jwt_audience: str = Field(pattern=r"^[A-Za-z0-9_.:-]{3,128}$")
    company_jwks_url: AnyHttpUrl
    applicant_session_ttl_seconds: int = Field(ge=300, le=86_400)
    invitation_public_base_url: AnyHttpUrl
    invitation_email_template: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,128}$")
    default_retention_days: int = Field(ge=1, le=3_650)
    signed_url_ttl_seconds: int = Field(ge=60, le=3_600)
    event_queue_url: SecretStr | None = None
    object_storage_bucket: str = Field(
        default="iep-local-contract-fixtures",
        pattern=r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$",
    )

    @model_validator(mode="after")
    def validate_regions(self) -> Settings:
        if not _AWS_REGION.fullmatch(self.aws_region):
            raise ValueError("aws_region must be a valid AWS region code")
        if not _AWS_REGION.fullmatch(self.bedrock_region):
            raise ValueError("bedrock_region must be a valid AWS region code")
        if self.bedrock_region != self.aws_region and not self.cross_region_model_approved:
            raise ValueError("cross-region model use requires explicit privacy approval")
        for url in (
            self.company_jwt_issuer,
            self.company_jwks_url,
            self.invitation_public_base_url,
        ):
            if url.username is not None or url.password is not None or url.query or url.fragment:
                raise ValueError(
                    "trusted configuration URLs cannot contain userinfo, query, or fragment"
                )
        return self

    def safe_snapshot(self) -> dict[str, Any]:
        snapshot: dict[str, Any] = {}
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, SecretStr):
                snapshot[field_name] = _REDACTED
            elif isinstance(value, AnyHttpUrl):
                snapshot[field_name] = str(value)
            elif isinstance(value, StrEnum):
                snapshot[field_name] = value.value
            else:
                snapshot[field_name] = value
        return snapshot

    def __repr__(self) -> str:
        return f"Settings({self.safe_snapshot()!r})"

    def __str__(self) -> str:
        return repr(self)
