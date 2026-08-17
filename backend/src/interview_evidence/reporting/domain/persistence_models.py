"""Register Lane D ORM models."""

from interview_evidence.reporting.repositories.postgres import (  # noqa: F401
    DeletionManifestRow,
    DeletionRequestRow,
    DeletionTargetRow,
    EvidenceRow,
    HumanReviewRow,
    RecordingAssetRow,
    ReportItemRow,
    ReportRow,
    SessionEventRow,
    TranscriptSegmentRow,
)
