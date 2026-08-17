"""Register Lane A ORM tables with the shared Alembic metadata registry."""

from interview_evidence.company_management.repositories.postgres import (  # noqa: F401
    ApplicantProfileRow,
    CampaignRow,
    CompanyRow,
    CompanyUserRow,
    CompetencyModelVersionRow,
    ConsentRecordRow,
    EvaluationCriterionRow,
    InvitationRow,
    PositionRow,
)
