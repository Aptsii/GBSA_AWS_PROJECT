from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_wheel_contains_generated_python_contracts(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    assert uv is not None
    result = subprocess.run(  # noqa: S603 - resolved trusted uv executable
        [uv, "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    wheel = next(tmp_path.glob("*.whl"))
    with ZipFile(wheel) as archive:
        members = set(archive.namelist())

    assert "interview_evidence_contracts/__init__.py" in members
    assert "interview_evidence_contracts/models.py" in members
    assert "interview_evidence_contracts/py.typed" in members
