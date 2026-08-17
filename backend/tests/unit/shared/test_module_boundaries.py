from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
CHECKER = REPOSITORY_ROOT / "scripts" / "check_module_boundaries.py"


def _run_checker(source_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and checker paths
        [sys.executable, str(CHECKER), str(source_root)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_public_cross_module_contract_import_is_allowed(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "company_management"
    source.mkdir(parents=True)
    (source / "service.py").write_text(
        "from interview_evidence.submission_analysis.contracts import StrategySnapshot\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 0, result.stdout + result.stderr


def test_private_cross_module_import_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "company_management"
    source.mkdir(parents=True)
    (source / "service.py").write_text(
        "from interview_evidence.submission_analysis.domain.strategy import InterviewStrategy\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "company_management" in result.stdout
    assert "submission_analysis.domain" in result.stdout


def test_interview_and_reporting_private_import_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "interview_engine"
    source.mkdir(parents=True)
    (source / "service.py").write_text(
        "from interview_evidence.reporting.repositories.postgres import ReportRepository\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "interview_engine" in result.stdout
    assert "reporting.repositories" in result.stdout


def test_relative_cross_module_private_import_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "company_management" / "application"
    source.mkdir(parents=True)
    (source / "service.py").write_text(
        "from ...submission_analysis.domain import strategy\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "submission_analysis.domain" in result.stdout


def test_composition_root_cannot_import_private_domain(tmp_path: Path) -> None:
    source_root = tmp_path / "interview_evidence"
    source_root.mkdir()
    (source_root / "main.py").write_text(
        "from interview_evidence.reporting.domain.report import Report\n",
        encoding="utf-8",
    )

    result = _run_checker(source_root)

    assert result.returncode == 1
    assert "composition" in result.stdout


def test_worker_may_use_its_own_domain_but_not_another_lane(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "workers" / "analysis"
    source.mkdir(parents=True)
    (source / "handler.py").write_text(
        "from interview_evidence.submission_analysis.domain.submission import Submission\n"
        "from interview_evidence.company_management.domain.company import Company\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "workers/analysis" in result.stdout
    assert "company_management.domain" in result.stdout


def test_constant_dynamic_private_import_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "shared"
    source.mkdir(parents=True)
    (source / "loader.py").write_text(
        "import importlib\n"
        "MODEL = importlib.import_module('interview_evidence.reporting.domain.report')\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "reporting.domain" in result.stdout


def test_aliased_dynamic_private_import_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "shared"
    source.mkdir(parents=True)
    (source / "loader.py").write_text(
        "from importlib import import_module\n"
        "MODEL = import_module('interview_evidence.reporting.domain.report')\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "reporting.domain" in result.stdout


def test_constant_variable_dynamic_private_import_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "shared"
    source.mkdir(parents=True)
    (source / "loader.py").write_text(
        "import importlib\n"
        "TARGET = 'interview_evidence.reporting.domain.report'\n"
        "MODEL = importlib.import_module(TARGET)\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "reporting.domain" in result.stdout


def test_cross_lane_raw_repository_query_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "interview_evidence" / "company_management" / "repositories"
    source.mkdir(parents=True)
    (source / "postgres.py").write_text(
        'QUERY = "SELECT * FROM interview_strategies WHERE company_id = :company_id"\n',
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "interview_strategies" in result.stdout
    assert "submission_analysis" in result.stdout


def test_unknown_root_module_is_rejected_instead_of_skipped(tmp_path: Path) -> None:
    source_root = tmp_path / "interview_evidence"
    source_root.mkdir()
    (source_root / "backdoor.py").write_text(
        "from interview_evidence.reporting.domain.report import Report\n",
        encoding="utf-8",
    )

    result = _run_checker(source_root)

    assert result.returncode == 1
    assert "unowned source path" in result.stdout
    assert "reporting.domain" in result.stdout


def test_cross_lane_raw_query_is_rejected_outside_repository_directories(
    tmp_path: Path,
) -> None:
    source = tmp_path / "interview_evidence" / "company_management" / "application"
    source.mkdir(parents=True)
    (source / "service.py").write_text(
        'QUERY = "SELECT * FROM interview_strategies WHERE company_id = :company_id"\n',
        encoding="utf-8",
    )

    result = _run_checker(tmp_path / "interview_evidence")

    assert result.returncode == 1
    assert "interview_strategies" in result.stdout


def test_root_schema_registry_cannot_bypass_private_domain_boundaries(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "interview_evidence"
    source_root.mkdir()
    (source_root / "schema_registry.py").write_text(
        "import importlib\n"
        "MODEL = importlib.import_module('interview_evidence.reporting.domain.report')\n",
        encoding="utf-8",
    )

    result = _run_checker(source_root)

    assert result.returncode == 1
    assert "unowned source path" in result.stdout
    assert "reporting.domain" in result.stdout
