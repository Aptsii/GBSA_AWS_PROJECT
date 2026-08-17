"""Opaque identifier, clock, and command metadata primitives."""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol, runtime_checkable
from uuid import UUID

_UUID7_RANDOM_BITS = 74
_UUID7_RANDOM_MASK = (1 << _UUID7_RANDOM_BITS) - 1
_MAX_UUID7_TIMESTAMP_MS = (1 << 48) - 1


class OpaqueId(str):
    """A validated UUIDv7 identifier whose value carries no business or PII meaning."""

    def __new__(cls, value: str | UUID) -> OpaqueId:
        parsed = value if isinstance(value, UUID) else UUID(str(value))
        if parsed.version != 7:
            raise ValueError("opaque identifiers must use UUID version 7")
        return str.__new__(cls, str(parsed))


@runtime_checkable
class Clock(Protocol):
    """UTC wall-clock interface used by deterministic domain tests and production code."""

    def now(self) -> datetime:
        """Return a timezone-aware instant."""


class SystemClock:
    """Production UTC clock."""

    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class FixedClock:
    """Deterministic clock fixed at one UTC-normalized instant."""

    instant: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "instant", _as_utc(self.instant))

    def now(self) -> datetime:
        return self.instant


class UUID7Generator:
    """Thread-safe UUIDv7 generator with injectable entropy for deterministic tests."""

    __slots__ = ("_clock", "_last_random", "_last_timestamp_ms", "_lock", "_randbytes")

    def __init__(
        self,
        clock: Clock | None = None,
        *,
        randbytes: Callable[[int], bytes] = secrets.token_bytes,
    ) -> None:
        self._clock = clock or SystemClock()
        self._randbytes = randbytes
        self._last_timestamp_ms = -1
        self._last_random = -1
        self._lock = Lock()

    def new(self) -> OpaqueId:
        timestamp_ms = int(_as_utc(self._clock.now()).timestamp() * 1000)
        if not 0 <= timestamp_ms <= _MAX_UUID7_TIMESTAMP_MS:
            raise ValueError("clock instant is outside the UUIDv7 timestamp range")

        with self._lock:
            if timestamp_ms > self._last_timestamp_ms:
                random_bytes = self._randbytes(10)
                if len(random_bytes) != 10:
                    raise ValueError("UUIDv7 entropy provider must return exactly 10 bytes")
                random_value = int.from_bytes(random_bytes, "big") & _UUID7_RANDOM_MASK
            else:
                timestamp_ms = self._last_timestamp_ms
                random_value = self._last_random + 1
                if random_value > _UUID7_RANDOM_MASK:
                    raise OverflowError("UUIDv7 monotonic entropy exhausted for one millisecond")

            self._last_timestamp_ms = timestamp_ms
            self._last_random = random_value

        random_a = random_value >> 62
        random_b = random_value & ((1 << 62) - 1)
        uuid_int = (timestamp_ms << 80) | (0x7 << 76) | (random_a << 64) | (0b10 << 62) | random_b
        return OpaqueId(UUID(int=uuid_int))

    def __repr__(self) -> str:
        return "UUID7Generator()"


@dataclass(frozen=True, slots=True)
class CommandMeta:
    """Metadata required for an idempotent, optionally version-checked command."""

    idempotency_key: str
    occurred_at: datetime
    expected_version: int | None = None

    def __post_init__(self) -> None:
        if not 16 <= len(self.idempotency_key) <= 128:
            raise ValueError("idempotency_key must contain between 16 and 128 characters")
        if any(character.isspace() for character in self.idempotency_key):
            raise ValueError("idempotency_key must not contain whitespace")
        if self.expected_version is not None and self.expected_version < 1:
            raise ValueError("expected_version must be a positive integer")
        object.__setattr__(self, "occurred_at", _as_utc(self.occurred_at))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)
