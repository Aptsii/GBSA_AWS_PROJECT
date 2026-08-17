from __future__ import annotations

import pytest
from interview_evidence.reporting.application.evidence_service import EvidenceService


def test_source_reference_cannot_be_promoted_without_final_applicant_answer() -> None:
    with pytest.raises(ValueError, match="final applicant Turn"):
        EvidenceService().validate_anchor(
            answer_turn_final=False,
            answer_speaker="applicant",
            transcript_within_turn=True,
            media_available=True,
            technical_failure=False,
        )
