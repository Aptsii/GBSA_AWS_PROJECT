from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from alembic.config import Config

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_CONFIG = REPOSITORY_ROOT / "backend" / "alembic.ini"
VERSIONS_ROOT = REPOSITORY_ROOT / "backend" / "alembic" / "versions"
MERGE_REVISION = VERSIONS_ROOT / "merge" / "m_001_lane_merge.py"
INTEGRATION_REVISION = VERSIONS_ROOT / "merge" / "m_002_shared_runtime.py"
LANES = {
    "company": "a_000_foundation.py",
    "submission": "b_000_foundation.py",
    "interview": "c_000_foundation.py",
    "reporting": "d_000_foundation.py",
}


def _load_revision(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _lane_migration_head(version_directory: Path) -> str:
    revisions: dict[str, str | None] = {}
    for path in version_directory.glob("*.py"):
        revision = _load_revision(path)
        if isinstance(revision.revision, str) and (
            revision.down_revision is None or isinstance(revision.down_revision, str)
        ):
            revisions[revision.revision] = revision.down_revision
    parents = {parent for parent in revisions.values() if parent is not None}
    heads = set(revisions) - parents
    assert len(heads) == 1
    return heads.pop()


def _next_lane_revision(current_head: str) -> str:
    prefix, separator, raw_number = current_head.rpartition("_")
    assert separator and raw_number.isdigit()
    return f"{prefix}_{int(raw_number) + 1:03d}"


def test_alembic_config_declares_each_lane_version_location() -> None:
    config = Config(str(ALEMBIC_CONFIG))
    locations = set(config.get_version_locations_list())

    assert locations == {
        *(str(VERSIONS_ROOT / lane) for lane in LANES),
        str(VERSIONS_ROOT / "merge"),
    }


def test_merge_revision_joins_the_current_lane_heads() -> None:
    merge_revision = _load_revision(MERGE_REVISION)
    lane_heads = tuple(
        _lane_migration_head(VERSIONS_ROOT / lane) for lane in LANES
    )

    assert merge_revision.revision == "m_001"
    assert merge_revision.down_revision == lane_heads
    assert merge_revision.branch_labels is None
    assert callable(merge_revision.upgrade)
    assert callable(merge_revision.downgrade)


def test_integration_runtime_revision_follows_the_lane_merge() -> None:
    integration_revision = _load_revision(INTEGRATION_REVISION)

    assert integration_revision.revision == "m_002"
    assert integration_revision.down_revision == "m_001"
    assert integration_revision.branch_labels is None
    assert callable(integration_revision.upgrade)
    assert callable(integration_revision.downgrade)


def test_each_lane_starts_with_one_reversible_labeled_head() -> None:
    for lane, filename in LANES.items():
        revision = _load_revision(VERSIONS_ROOT / lane / filename)

        assert revision.revision.startswith(filename[0:2])
        assert revision.down_revision is None
        assert revision.branch_labels == (lane,)
        assert callable(revision.upgrade)
        assert callable(revision.downgrade)


def test_migration_validation_gate_passes() -> None:
    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(REPOSITORY_ROOT / "scripts" / "check_migrations.sh")],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "prefixes" in result.stdout
    assert "downgrade" in result.stdout
    assert "ORM drift" in result.stdout
    assert "previous snapshot" in result.stdout


def test_migration_gate_requires_a_new_merge_for_a_new_lane_head(tmp_path: Path) -> None:
    temporary_backend = tmp_path / "backend"
    shutil.copytree(REPOSITORY_ROOT / "backend" / "alembic", temporary_backend / "alembic")
    shutil.copy2(ALEMBIC_CONFIG, temporary_backend / "alembic.ini")
    temporary_package = temporary_backend / "src" / "interview_evidence"
    shutil.copytree(
        REPOSITORY_ROOT / "backend" / "src" / "interview_evidence",
        temporary_package,
    )
    domain_package = temporary_package / "company_management" / "domain"
    domain_package.mkdir(parents=True, exist_ok=True)
    (domain_package.parent / "__init__.py").touch()
    (domain_package / "__init__.py").touch()
    (domain_package / "sample.py").write_text(
        "from sqlalchemy.orm import Mapped, mapped_column\n"
        "from interview_evidence.shared.database import Base\n"
        "class SampleEntity(Base):\n"
        "    __tablename__ = 'sample_entities'\n"
        "    id: Mapped[int] = mapped_column(primary_key=True)\n",
        encoding="utf-8",
    )
    company_versions = temporary_backend / "alembic" / "versions" / "company"
    current_head = _lane_migration_head(company_versions)
    next_revision = _next_lane_revision(current_head)
    (company_versions / f"{next_revision}_next.py").write_text(
        '"""Test-only successor revision."""\n'
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        f'revision = "{next_revision}"\n'
        f'down_revision = "{current_head}"\n'
        "branch_labels = None\n"
        "depends_on = None\n"
        "def upgrade():\n"
        "    op.create_table('sample_entities', sa.Column('id', sa.Integer(), primary_key=True))\n"
        "def downgrade():\n"
        "    op.drop_table('sample_entities')\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["FOUNDATION_ALEMBIC_CONFIG"] = str(temporary_backend / "alembic.ini")

    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(REPOSITORY_ROOT / "scripts" / "check_migrations.sh")],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "merge revision parents" in result.stderr
    assert next_revision in result.stderr


def _run_temporary_migration_gate(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    temporary_backend = tmp_path / "backend"
    shutil.copytree(REPOSITORY_ROOT / "backend" / "alembic", temporary_backend / "alembic")
    shutil.copy2(ALEMBIC_CONFIG, temporary_backend / "alembic.ini")
    environment = os.environ.copy()
    environment["FOUNDATION_ALEMBIC_CONFIG"] = str(temporary_backend / "alembic.ini")
    return temporary_backend, environment


def test_migration_gate_rejects_a_wrong_prefix_in_the_middle_of_a_lane(
    tmp_path: Path,
) -> None:
    temporary_backend, environment = _run_temporary_migration_gate(tmp_path)
    company_versions = temporary_backend / "alembic" / "versions" / "company"
    (company_versions / "x_001_wrong_owner.py").write_text(
        'revision = "x_001"\n'
        'down_revision = "a_000"\n'
        "branch_labels = None\n"
        "depends_on = None\n"
        "def upgrade(): pass\n"
        "def downgrade(): pass\n",
        encoding="utf-8",
    )
    (company_versions / "a_002_head.py").write_text(
        'revision = "a_002"\n'
        'down_revision = "x_001"\n'
        "branch_labels = None\n"
        "depends_on = None\n"
        "def upgrade(): pass\n"
        "def downgrade(): pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(REPOSITORY_ROOT / "scripts" / "check_migrations.sh")],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "wrong prefix" in result.stderr
    assert "x_001" in result.stderr


def test_destructive_upgrade_requires_a_data_migration_note(tmp_path: Path) -> None:
    temporary_backend, environment = _run_temporary_migration_gate(tmp_path)
    company_versions = temporary_backend / "alembic" / "versions" / "company"
    (company_versions / "a_001_destructive.py").write_text(
        "from alembic import op\n"
        'revision = "a_001"\n'
        'down_revision = "a_000"\n'
        "branch_labels = None\n"
        "depends_on = None\n"
        "def upgrade(): op.drop_table('legacy_applicant_answers')\n"
        "def downgrade(): pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(REPOSITORY_ROOT / "scripts" / "check_migrations.sh")],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "data_migration_note" in result.stderr


@pytest.mark.parametrize(
    "imports,constant,operation",
    [
        (
            "import sqlalchemy as sa\nfrom alembic import op\n",
            "",
            "op.execute(sa.text('DELETE FROM applicant_profiles'))",
        ),
        (
            "from alembic import op\n",
            "DESTRUCTIVE_SQL = 'DROP TABLE applicant_profiles'\n",
            "op.execute(DESTRUCTIVE_SQL)",
        ),
        (
            "from alembic import op\n",
            "",
            "op.alter_column('applicant_profiles', 'display_name', type_='VARCHAR(8)')",
        ),
        (
            "from alembic import op\n",
            "",
            "op.alter_column('applicant_profiles', 'display_name', nullable=False)",
        ),
    ],
)
def test_destructive_upgrade_policy_rejects_common_indirect_forms(
    tmp_path: Path,
    imports: str,
    constant: str,
    operation: str,
) -> None:
    temporary_backend, environment = _run_temporary_migration_gate(tmp_path)
    company_versions = temporary_backend / "alembic" / "versions" / "company"
    (company_versions / "a_001_destructive.py").write_text(
        f"{imports}"
        'revision = "a_001"\n'
        'down_revision = "a_000"\n'
        "branch_labels = None\n"
        "depends_on = None\n"
        f"{constant}"
        f"def upgrade(): {operation}\n"
        "def downgrade(): pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(REPOSITORY_ROOT / "scripts" / "check_migrations.sh")],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "data_migration_note" in result.stderr


def test_migration_gate_rejects_schema_residue_after_downgrade(tmp_path: Path) -> None:
    temporary_backend, environment = _run_temporary_migration_gate(tmp_path)
    env_path = temporary_backend / "alembic" / "env.py"
    env_source = env_path.read_text(encoding="utf-8")
    env_path.write_text(
        env_source.replace(
            "target_metadata = load_domain_metadata()",
            "target_metadata = load_domain_metadata()\n"
            "sa.Table('leftover_table', target_metadata, "
            "sa.Column('id', sa.Integer(), primary_key=True))",
        ).replace(
            "from alembic import context",
            "import sqlalchemy as sa\nfrom alembic import context",
        ),
        encoding="utf-8",
    )
    baseline = temporary_backend / "alembic" / "versions" / "company" / "a_000_foundation.py"
    baseline.write_text(
        "import sqlalchemy as sa\n"
        "from alembic import op\n"
        'revision = "a_000"\n'
        "down_revision = None\n"
        'branch_labels = ("company",)\n'
        "depends_on = None\n"
        "def upgrade():\n"
        "    op.create_table('leftover_table', sa.Column('id', sa.Integer(), primary_key=True))\n"
        "def downgrade(): pass\n",
        encoding="utf-8",
    )

    result = subprocess.run(  # noqa: S603 - fixed repository script path
        [str(REPOSITORY_ROOT / "scripts" / "check_migrations.sh")],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "schema objects remain after downgrade" in result.stderr
