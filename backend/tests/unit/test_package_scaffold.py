from __future__ import annotations

import subprocess
import sys

import interview_evidence


def test_backend_package_is_importable_without_domain_side_effects() -> None:
    assert interview_evidence.__all__ == ()


def test_unwired_worker_entrypoint_fails_closed_with_a_safe_message() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "interview_evidence.workers"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.strip() == (
        "No worker handlers are registered; complete T176 before launch."
    )
