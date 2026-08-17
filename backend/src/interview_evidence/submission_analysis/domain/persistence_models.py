"""Register Lane B ORM tables with the shared Alembic metadata registry."""

from interview_evidence.submission_analysis.repositories.postgres import (  # noqa: F401
    CandidateCodeUnitRow,
    GitCommitAnalysisRow,
    GitRepositoryAnalysisRow,
    InterviewStrategyRow,
    SubmissionAnalysisRow,
    SubmissionRow,
    SubmissionSourceReferenceRow,
)
