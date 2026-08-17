from __future__ import annotations

import os
import subprocess
import sys
import time

import interview_evidence


def test_backend_package_is_importable_without_domain_side_effects() -> None:
    assert interview_evidence.__all__ == ()


def test_worker_entrypoint_stays_alive_until_shutdown_signal() -> None:
    environment = {
        **os.environ,
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_ENDPOINT_URL": "http://127.0.0.1:9",
        "AWS_MAX_ATTEMPTS": "1",
        "AWS_RETRY_MODE": "standard",
        "NO_PROXY": "127.0.0.1,localhost",
        "IEP_ENVIRONMENT": "test",
        "IEP_DATABASE_URL": "sqlite+pysqlite:///:memory:",
        "IEP_APPLICANT_SESSION_SECRET": "applicant-session-secret-value",
        "IEP_COMPANY_JWT_ISSUER": "https://identity.example.invalid/tenant",
        "IEP_COMPANY_JWT_AUDIENCE": "interview-evidence-api",
        "IEP_COMPANY_JWKS_URL": "https://identity.example.invalid/tenant/jwks.json",
        "IEP_APPLICANT_SESSION_TTL_SECONDS": "1800",
        "IEP_INVITATION_PUBLIC_BASE_URL": "https://interview.example.invalid",
        "IEP_INVITATION_EMAIL_TEMPLATE": "applicant-invitation-v1",
        "IEP_DEFAULT_RETENTION_DAYS": "180",
        "IEP_SIGNED_URL_TTL_SECONDS": "300",
        "IEP_EVENT_QUEUE_URL": "http://127.0.0.1:9/000000000000/events",
        "IEP_EVENT_DLQ_URL": "http://127.0.0.1:9/000000000000/events-dlq",
        "IEP_WORKER_WAIT_TIME_SECONDS": "0",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "interview_evidence.workers"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
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
    assert stderr.splitlines()
    assert set(stderr.splitlines()) == {"Worker receive failed; retrying."}
