from __future__ import annotations

import hashlib

import pytest
from interview_evidence.interview_engine.application.recording_service import RecordingService
from interview_evidence.shared.aws_clients.ports import ProtectedBytes
from interview_evidence.shared.tenant import ApplicantScope, TenantContext

from tests.fixtures.shared.factories import (
    APPLICANT_ID,
    COMPANY_ID,
    INVITATION_ID,
    SESSION_ID,
    make_tenant_context,
)


def test_recording_chunks_verify_digest_sequence_and_resume() -> None:
    service = RecordingService()
    context = TenantContext(**make_tenant_context())
    scope = ApplicantScope(COMPANY_ID, APPLICANT_ID, INVITATION_ID)
    payload = b"audio"
    service.accept(
        context,
        scope,
        SESSION_ID,
        sequence=1,
        content=ProtectedBytes(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        start_ms=0,
        end_ms=1000,
        idempotency_key="recording-chunk-0001",
    )
    assert service.last_verified_sequence(context, scope, SESSION_ID) == 1
    with pytest.raises(ValueError, match="sequence"):
        service.accept(
            context,
            scope,
            SESSION_ID,
            sequence=3,
            content=ProtectedBytes(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            start_ms=1000,
            end_ms=2000,
            idempotency_key="recording-chunk-0002",
        )
