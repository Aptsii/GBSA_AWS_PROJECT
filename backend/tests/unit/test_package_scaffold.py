from __future__ import annotations

import subprocess
import sys
import time

import interview_evidence


def test_backend_package_is_importable_without_domain_side_effects() -> None:
    assert interview_evidence.__all__ == ()


def test_worker_entrypoint_stays_alive_until_shutdown_signal() -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "interview_evidence.workers"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(1)
        assert process.poll() is None
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)

    assert process.returncode == 0
    assert stdout == ""
    assert stderr == ""
