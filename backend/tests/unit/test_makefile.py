from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

QUICKSTART_TARGETS = (
    "bootstrap",
    "compose-up",
    "migrate",
    "seed-contract-fixtures",
    "contracts-generate",
    "contracts-check",
    "boundaries-check",
    "migration-check",
    "test-foundation",
    "test-lane-a",
    "demo-lane-a",
    "test-lane-b",
    "demo-lane-b",
    "test-lane-c",
    "demo-lane-c",
    "test-lane-d",
    "demo-lane-d",
    "test-integration",
    "test-e2e-thin",
    "test-recovery",
    "test-tenant-isolation",
    "test-deletion-residue",
    "test-ai-regression",
    "test-load-pilot",
    "infra-format-check",
    "infra-validate",
    "infra-security-check",
    "infra-plan-dev",
    "test-prior-lanes",
)


@pytest.mark.parametrize("target", QUICKSTART_TARGETS)
def test_every_quickstart_make_target_is_declared(target: str) -> None:
    make = shutil.which("make")
    assert make is not None
    result = subprocess.run(  # noqa: S603 - fixed make binary and repository-owned target
        [make, "--dry-run", target],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip()
