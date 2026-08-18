from __future__ import annotations

import pytest
from interview_evidence.interview_engine.api.websocket import ProtocolMessage


def test_websocket_envelope_requires_version_sequence_and_idempotency() -> None:
    message = ProtocolMessage.model_validate(
        {
            "protocol_version": "1.0",
            "message_type": "answer.complete",
            "session_id": "018f2000-0000-7000-8000-000000000230",
            "sequence": 3,
            "idempotency_key": "answer-complete-0001",
            "correlation_id": "018f2000-0000-7000-8000-000000000231",
            "sent_at": "2026-08-17T00:00:00Z",
            "payload": {"answer_turn_id": "018f2000-0000-7000-8000-000000000232"},
        }
    )
    assert message.protocol_version == "1.0"
    assert message.sequence == 3


def test_websocket_envelope_rejects_unknown_protocol_and_extra_fields() -> None:
    with pytest.raises(ValueError):
        ProtocolMessage.model_validate(
            {
                "protocol_version": "2.0",
                "message_type": "answer.complete",
                "session_id": "018f2000-0000-7000-8000-000000000230",
                "sequence": 0,
                "idempotency_key": "answer-complete-0002",
                "correlation_id": "018f2000-0000-7000-8000-000000000231",
                "sent_at": "2026-08-17T00:00:00Z",
                "payload": {},
                "unexpected": True,
            }
        )


def test_websocket_envelope_accepts_versioned_three_part_audio_message() -> None:
    message = ProtocolMessage.model_validate(
        {
            "protocol_version": "1.0",
            "message_type": "audio.chunk.begin",
            "session_id": "018f2000-0000-7000-8000-000000000230",
            "sequence": 3,
            "idempotency_key": "audio-chunk-begin-0001",
            "correlation_id": "018f2000-0000-7000-8000-000000000231",
            "sent_at": "2026-08-17T00:00:00Z",
            "payload": {
                "answer_turn_id": "018f2000-0000-7000-8000-000000000232",
                "chunk_sequence": 1,
            },
        }
    )

    assert message.message_type == "audio.chunk.begin"
