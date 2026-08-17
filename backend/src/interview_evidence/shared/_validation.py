"""Internal validation helpers for identifier-only operational payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Final

type Scalar = str | int | float | bool | None
type FrozenValue = Scalar | tuple[FrozenValue, ...] | Mapping[str, FrozenValue]

_SAFE_KEY: Final = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_SAFE_VALUE: Final = re.compile(r"^[A-Za-z0-9_.:@+-]{1,256}$")
_OPAQUE_UUID: Final = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_TRACE_HEX: Final = re.compile(r"^[0-9a-f]{16}(?:[0-9a-f]{16})?$")
_COMPACT_TOKEN: Final = re.compile(r"^(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9]{20,}$")
_PROHIBITED_EXACT: Final = frozenset(
    {
        "answer",
        "answer_text",
        "applicant_email",
        "applicant_name",
        "audio",
        "audio_url",
        "body",
        "credential",
        "credentials",
        "document",
        "document_text",
        "email",
        "invitation_token",
        "password",
        "prompt",
        "raw_content",
        "raw_text",
        "secret",
        "signed_url",
        "source_text",
        "text",
        "token",
        "transcript",
        "transcript_text",
        "url",
        "video_url",
    }
)
_PROHIBITED_PARTS: Final = ("credential", "password", "signed_url", "secret", "token")


def utc_instant(value: datetime, *, field_name: str = "timestamp") -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(UTC)


def safe_code(value: str, *, field_name: str, max_length: int = 128) -> str:
    if not value or len(value) > max_length or not _SAFE_VALUE.fullmatch(value):
        raise ValueError(f"{field_name} must be an opaque safe code")
    return value


def freeze_operational_payload(
    value: Mapping[str, object],
    *,
    label: str = "operational payload",
) -> Mapping[str, FrozenValue]:
    return MappingProxyType(
        {
            validated_key: _freeze_value(item, label=label, field_name=validated_key)
            for key, item in value.items()
            for validated_key in (_validate_key(key, label=label),)
        }
    )


def _validate_key(key: object, *, label: str) -> str:
    if not isinstance(key, str) or not _SAFE_KEY.fullmatch(key):
        raise ValueError(f"{label} contains an invalid key")
    normalized = key.casefold()
    if (
        normalized in _PROHIBITED_EXACT
        or normalized.endswith("_text")
        or any(part in normalized for part in _PROHIBITED_PARTS)
    ):
        raise ValueError(f"{label} contains a prohibited field")
    return key


def _freeze_value(value: object, *, label: str, field_name: str | None = None) -> FrozenValue:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{label} contains a non-finite number")
        return value
    if isinstance(value, str):
        if not _SAFE_VALUE.fullmatch(value) or "://" in value:
            raise ValueError(f"{label} strings must be opaque IDs or sanitized codes")
        normalized = value.casefold()
        if any(part in normalized for part in _PROHIBITED_PARTS):
            raise ValueError(f"{label} contains a secret-shaped value")
        if (
            _COMPACT_TOKEN.fullmatch(value)
            and _OPAQUE_UUID.fullmatch(normalized) is None
            and _TRACE_HEX.fullmatch(normalized) is None
        ):
            raise ValueError(f"{label} contains a token-shaped value")
        return value
    if isinstance(value, Mapping):
        return freeze_operational_payload(value, label=label)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item, label=label, field_name=field_name) for item in value)
    raise ValueError(f"{label} contains an unsupported value")


def plain_operational_value(value: FrozenValue) -> object:
    if isinstance(value, Mapping):
        return {key: plain_operational_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [plain_operational_value(item) for item in value]
    return value


def plain_operational_payload(value: Mapping[str, FrozenValue]) -> dict[str, object]:
    return {key: plain_operational_value(item) for key, item in value.items()}
