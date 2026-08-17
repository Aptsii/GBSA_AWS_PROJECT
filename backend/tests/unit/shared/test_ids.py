from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import UUID

import pytest
from interview_evidence.shared.ids import CommandMeta, FixedClock, UUID7Generator

NOW = datetime(2026, 8, 14, 12, 30, tzinfo=UTC)


def test_uuid7_generator_is_opaque_deterministic_and_monotonic() -> None:
    generator = UUID7Generator(FixedClock(NOW), randbytes=lambda size: b"\x00" * size)

    first = generator.new()
    second = generator.new()

    assert UUID(first).version == 7
    assert UUID(second).version == 7
    assert first < second
    assert str(first) == "01a00040-2940-7000-8000-000000000000"


def test_clock_and_command_metadata_require_utc_aware_values() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(datetime(2026, 8, 14, 12, 30))

    meta = CommandMeta(
        idempotency_key="operation-key-0001",
        expected_version=3,
        occurred_at=NOW,
    )

    assert meta.occurred_at.tzinfo is UTC
    with pytest.raises(FrozenInstanceError):
        meta.expected_version = 4  # type: ignore[misc]


@pytest.mark.parametrize("key", ["short", "x" * 129])
def test_command_metadata_rejects_unsafe_idempotency_keys(key: str) -> None:
    with pytest.raises(ValueError, match="idempotency_key"):
        CommandMeta(idempotency_key=key, occurred_at=NOW)


def test_command_metadata_rejects_non_positive_expected_version() -> None:
    with pytest.raises(ValueError, match="expected_version"):
        CommandMeta(
            idempotency_key="operation-key-0001",
            expected_version=0,
            occurred_at=NOW,
        )
