from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
VERIFY_SCRIPT = REPOSITORY_ROOT / "scripts" / "verify_foundation.sh"
GIT = shutil.which("git")
assert GIT is not None

FOUNDATION_ARTIFACTS = (
    ".editorconfig",
    ".github/workflows/ci.yml",
    "Makefile",
    "backend/Containerfile",
    "backend/alembic.ini",
    "backend/alembic/env.py",
    "backend/src/interview_evidence/main.py",
    "backend/src/interview_evidence/shared/audit.py",
    "backend/src/interview_evidence/shared/aws_clients/ports.py",
    "backend/src/interview_evidence/shared/config.py",
    "backend/src/interview_evidence/shared/errors.py",
    "backend/src/interview_evidence/shared/ids.py",
    "backend/src/interview_evidence/shared/messaging/outbox.py",
    "backend/src/interview_evidence/shared/observability.py",
    "backend/src/interview_evidence/shared/security/principals.py",
    "backend/src/interview_evidence/shared/tenant.py",
    "backend/tests/contract/test_generated_contract_drift.py",
    "packages/contracts/events/catalog.v1.json",
    "packages/contracts/events/common/v1/envelope.json",
    "packages/contracts/events/websocket/v1/catalog.json",
    "packages/contracts/generated/README.md",
    "packages/contracts/modules/v1/catalog.json",
    "packages/contracts/openapi/root.yaml",
    "packages/contracts/scripts/generate_contracts.py",
    "scripts/check_migrations.sh",
    "scripts/check_module_boundaries.py",
    "tests/fixtures/shared/factories.py",
    "apps/company-console/src/app/featureRoutes.ts",
    "apps/applicant-interview/src/app/featureRoutes.ts",
)
EXECUTABLE_ARTIFACTS = (
    "scripts/check_migrations.sh",
    "scripts/check_module_boundaries.py",
)


def test_foundation_gate_lists_every_frozen_boundary() -> None:
    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(VERIFY_SCRIPT), "--list"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for gate in (
        "format",
        "typecheck",
        "unit-tests",
        "contract-drift",
        "module-boundaries",
        "migration-branches",
        "working-tree",
        "foundation-v1-tag",
    ):
        assert gate in result.stdout


def test_foundation_gate_rejects_unknown_mode() -> None:
    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(VERIFY_SCRIPT), "--unknown"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2


def test_ci_runs_contract_boundary_and_migration_gates() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    for command in ("make test-contract", "make boundaries-check", "make migration-check"):
        assert command in workflow


def test_ci_node_runtime_satisfies_the_package_manager_minimum() -> None:
    manifest = json.loads((REPOSITORY_ROOT / "package.json").read_text(encoding="utf-8"))
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    minimum = tuple(int(part) for part in manifest["engines"]["node"].removeprefix(">=").split("."))
    match = re.search(r'^\s*NODE_VERSION:\s*"([0-9]+(?:\.[0-9]+){2})"$', workflow, re.M)

    assert minimum >= (22, 13, 0)
    assert match is not None
    runtime = tuple(int(part) for part in match.group(1).split("."))
    assert runtime >= minimum


def test_contract_workspace_participates_in_root_typechecking() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "packages" / "contracts" / "package.json").read_text(encoding="utf-8")
    )

    assert manifest["scripts"]["typecheck"]
    assert manifest["devDependencies"]["typescript"]


def test_pre_tag_rejects_dirty_worktree_without_creating_tag(tmp_path: Path) -> None:
    repository, script, environment = _create_ready_repository(tmp_path)
    dirty_file = repository / "untracked-change.txt"
    dirty_file.write_text("must remain untouched\n", encoding="utf-8")
    tags_before = _tag_snapshot(repository)

    result = _run_gate(repository, script, environment, "--pre-tag")

    assert result.returncode == 1
    assert "working tree must contain no tracked or untracked changes" in result.stderr
    assert _tag_snapshot(repository) == tags_before == ""
    assert dirty_file.read_text(encoding="utf-8") == "must remain untouched\n"


def test_pre_tag_rejects_existing_tag_without_moving_or_deleting_it(tmp_path: Path) -> None:
    repository, script, environment = _create_ready_repository(tmp_path)
    _git(repository, "tag", "-a", "foundation-v1", "-m", "existing foundation")
    tags_before = _tag_snapshot(repository)

    result = _run_gate(repository, script, environment, "--pre-tag")

    assert result.returncode == 1
    assert "foundation-v1 already exists" in result.stderr
    assert "will not move or delete it" in result.stderr
    assert _tag_snapshot(repository) == tags_before


def test_post_tag_rejects_missing_tag_without_creating_it(tmp_path: Path) -> None:
    repository, script, environment = _create_ready_repository(tmp_path)
    tags_before = _tag_snapshot(repository)

    result = _run_gate(repository, script, environment, "--post-tag")

    assert result.returncode == 1
    assert "foundation-v1 does not exist" in result.stderr
    assert _tag_snapshot(repository) == tags_before == ""


def test_post_tag_rejects_lightweight_tag_without_replacing_it(tmp_path: Path) -> None:
    repository, script, environment = _create_ready_repository(tmp_path)
    _git(repository, "tag", "foundation-v1")
    tags_before = _tag_snapshot(repository)

    result = _run_gate(repository, script, environment, "--post-tag")

    assert result.returncode == 1
    assert "foundation-v1 must be an annotated or signed tag" in result.stderr
    assert _tag_snapshot(repository) == tags_before


def test_post_tag_rejects_tag_at_wrong_head_without_moving_it(tmp_path: Path) -> None:
    repository, script, environment = _create_ready_repository(tmp_path)
    _git(repository, "tag", "-a", "foundation-v1", "-m", "old foundation")
    (repository / "later-commit.txt").write_text("later\n", encoding="utf-8")
    _git(repository, "add", "later-commit.txt")
    _git(repository, "commit", "-qm", "later commit")
    tags_before = _tag_snapshot(repository)

    result = _run_gate(repository, script, environment, "--post-tag")

    assert result.returncode == 1
    assert "foundation-v1 does not point to current HEAD" in result.stderr
    assert _tag_snapshot(repository) == tags_before


def test_pre_and_post_tag_success_paths_do_not_mutate_tag_refs(tmp_path: Path) -> None:
    repository, script, environment = _create_ready_repository(tmp_path)

    pre_result = _run_gate(repository, script, environment, "--pre-tag")

    assert pre_result.returncode == 0, pre_result.stdout + pre_result.stderr
    assert "Manual next step: git tag -a foundation-v1" in pre_result.stdout
    assert _tag_snapshot(repository) == ""

    _git(repository, "tag", "-a", "foundation-v1", "-m", "approved foundation")
    tags_before = _tag_snapshot(repository)

    post_result = _run_gate(repository, script, environment, "--post-tag")

    assert post_result.returncode == 0, post_result.stdout + post_result.stderr
    assert "foundation-v1 verified" in post_result.stdout
    assert _tag_snapshot(repository) == tags_before


def _create_ready_repository(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    repository = tmp_path / "repository"
    repository.mkdir()
    script = repository / "scripts" / "verify_foundation.sh"
    script.parent.mkdir(parents=True)
    shutil.copy2(VERIFY_SCRIPT, script)

    for relative_path in FOUNDATION_ARTIFACTS:
        artifact = repository / relative_path
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.touch()
    for relative_path in EXECUTABLE_ARTIFACTS:
        (repository / relative_path).chmod(0o755)

    for generated_directory in (
        "packages/contracts/generated/python",
        "packages/contracts/generated/typescript",
    ):
        (repository / generated_directory).mkdir(parents=True)

    feature_directory = repository / "specs" / "001-interview-evidence-platform"
    checklist_directory = feature_directory / "checklists"
    checklist_directory.mkdir(parents=True)
    (checklist_directory / "parallel-readiness.md").write_text(
        "- [x] temporary fixture reviewed\n",
        encoding="utf-8",
    )
    (feature_directory / "tasks.md").write_text(
        "- [X] T001-T034 accepted in temporary fixture\n",
        encoding="utf-8",
    )

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for command in ("make", "uv", "pnpm", "terraform", "docker"):
        executable = fake_bin / command
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"

    _git(repository, "init", "-q")
    _git(repository, "config", "user.name", "Foundation Gate Test")
    _git(repository, "config", "user.email", "foundation-gate@example.invalid")
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "foundation fixture")
    return repository, script, environment


def _run_gate(
    repository: Path,
    script: Path,
    environment: dict[str, str],
    mode: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - copied repository-owned script in an isolated repo
        [str(script), mode],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _git(
    repository: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - resolved trusted Git executable
        [GIT, *arguments],
        cwd=repository,
        check=check,
        capture_output=True,
        text=True,
    )


def _tag_snapshot(repository: Path) -> str:
    result = _git(repository, "show-ref", "--dereference", "--tags", check=False)
    assert result.returncode in (0, 1), result.stderr
    return result.stdout
