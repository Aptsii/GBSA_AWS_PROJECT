from __future__ import annotations

from interview_evidence.interview_engine.adapters.transcribe import StreamingTranscriber


def test_partial_transcript_is_display_only_and_final_can_be_persisted() -> None:
    transcriber = StreamingTranscriber(review_threshold=0.7)
    partial = transcriber.result("중간", confidence=0.9, is_final=False)
    final = transcriber.result("최종", confidence=0.6, is_final=True)
    assert partial.evidence_eligible is False
    assert final.evidence_eligible is True
    assert final.review_required is True
