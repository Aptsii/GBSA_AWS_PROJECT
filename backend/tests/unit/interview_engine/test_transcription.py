from __future__ import annotations

import pytest
from interview_evidence.interview_engine.adapters.transcribe import (
    StreamingTranscriber,
    Utf8TextTranscriber,
)
from interview_evidence.shared.aws_clients.ports import ProtectedBytes, TranscriptionRequest
from interview_evidence.shared.ids import OpaqueId
from interview_evidence.shared.tenant import TenantContext

from tests.fixtures.shared.factories import COMPANY_ID, make_tenant_context


def test_partial_transcript_is_display_only_and_final_can_be_persisted() -> None:
    transcriber = StreamingTranscriber(review_threshold=0.7)
    partial = transcriber.result("중간", confidence=0.9, is_final=False)
    final = transcriber.result("최종", confidence=0.6, is_final=True)
    assert partial.evidence_eligible is False
    assert final.evidence_eligible is True
    assert final.review_required is True


@pytest.mark.asyncio
async def test_local_utf8_transcriber_returns_protected_final_text() -> None:
    result = await Utf8TextTranscriber().transcribe(
        TenantContext(**make_tenant_context()),
        TranscriptionRequest(
            company_id=COMPANY_ID,
            request_id=OpaqueId("018f2000-0000-7000-8000-000000000402"),
            audio=ProtectedBytes("텍스트 전사 입력".encode()),
            config_version="stt-v1",
        ),
    )

    assert result.text.reveal() == "텍스트 전사 입력"
    assert result.confidence == 1.0
    assert result.review_required is False
