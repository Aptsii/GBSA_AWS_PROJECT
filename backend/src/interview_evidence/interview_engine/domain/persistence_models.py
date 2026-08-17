"""Register Lane C ORM tables with the shared Alembic metadata registry."""

from interview_evidence.interview_engine.repositories.postgres import (  # noqa: F401
    InterviewSessionRow,
    RecordingChunkRow,
    SessionCheckpointRow,
    TurnRow,
)
