from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from interview_evidence.shared.errors import (
    ErrorCode,
    FieldError,
    SafeApplicationError,
    build_error_envelope,
)

REQUEST_ID = "0198a82a-0540-7000-8000-000000000005"


def test_error_envelope_comes_only_from_the_safe_catalog() -> None:
    envelope = build_error_envelope(
        ErrorCode.DEPENDENCY_TIMEOUT,
        request_id=REQUEST_ID,
    )

    assert envelope.to_dict() == {
        "type": "urn:interview-evidence:error:dependency-timeout",
        "title": "Dependency timed out",
        "status": 503,
        "code": "DEPENDENCY_TIMEOUT",
        "detail": "A required service did not respond in time.",
        "request_id": REQUEST_ID,
        "retryable": True,
    }
    with pytest.raises(FrozenInstanceError):
        envelope.retryable = False  # type: ignore[misc]


def test_safe_application_error_never_renders_runtime_exception_text() -> None:
    raw_secret = "postgresql://admin:secret@example.invalid/app"
    error = SafeApplicationError(
        ErrorCode.INTERNAL_ERROR,
        cause=RuntimeError(raw_secret),
    )

    rendered = repr(error) + str(error)
    assert raw_secret not in rendered
    assert "INTERNAL_ERROR" in rendered


def test_field_errors_are_code_only_and_current_version_is_supported() -> None:
    envelope = build_error_envelope(
        ErrorCode.STALE_VERSION,
        request_id=REQUEST_ID,
        current_version=4,
        field_errors=(FieldError(field="body.expected_version", code="stale"),),
    )

    assert envelope.to_dict()["current_version"] == 4
    assert envelope.to_dict()["errors"] == [{"field": "body.expected_version", "code": "stale"}]

    with pytest.raises(ValueError, match="field"):
        FieldError(field="body;token", code="invalid")
