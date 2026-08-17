"""Create company, hiring, invitation, and consent tables."""

from alembic import op
import sqlalchemy as sa

revision = "a_001"
down_revision = "a_000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("company_id", name=op.f("pk_companies")),
    )
    op.create_table(
        "company_users",
        sa.Column("company_user_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("identity_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("roles", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("company_user_id", name=op.f("pk_company_users")),
        sa.UniqueConstraint(
            "company_id",
            "email",
            name="uq_company_users_company_email",
        ),
        sa.UniqueConstraint(
            "company_id",
            "identity_subject",
            name="uq_company_users_company_identity_subject",
        ),
    )
    op.create_index(
        op.f("ix_company_users_company_id"),
        "company_users",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "positions",
        sa.Column("position_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("position_id", name=op.f("pk_positions")),
        sa.UniqueConstraint(
            "company_id",
            "position_id",
            name="uq_positions_company_position",
        ),
    )
    op.create_index(
        op.f("ix_positions_company_id"),
        "positions",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "competency_model_versions",
        sa.Column("competency_model_version_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("prohibited_topics", sa.JSON(), nullable=False),
        sa.Column("interview_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("persona_definition", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["positions.company_id", "positions.position_id"],
            name="fk_competency_versions_position",
        ),
        sa.PrimaryKeyConstraint(
            "competency_model_version_id",
            name=op.f("pk_competency_model_versions"),
        ),
        sa.UniqueConstraint(
            "company_id",
            "competency_model_version_id",
            name="uq_competency_versions_company_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "position_id",
            "version_number",
            name="uq_competency_versions_position_number",
        ),
    )
    op.create_index(
        op.f("ix_competency_model_versions_company_id"),
        "competency_model_versions",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "evaluation_criteria",
        sa.Column("criterion_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("competency_model_version_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("good_evidence", sa.JSON(), nullable=False),
        sa.Column("weak_evidence", sa.JSON(), nullable=False),
        sa.Column("abstain_guidance", sa.Text(), nullable=False),
        sa.Column("common_questions", sa.JSON(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "competency_model_version_id"],
            [
                "competency_model_versions.company_id",
                "competency_model_versions.competency_model_version_id",
            ],
            name="fk_evaluation_criteria_version",
        ),
        sa.PrimaryKeyConstraint("criterion_id", name=op.f("pk_evaluation_criteria")),
        sa.UniqueConstraint(
            "company_id",
            "competency_model_version_id",
            "code",
            name="uq_evaluation_criteria_version_code",
        ),
    )
    op.create_index(
        op.f("ix_evaluation_criteria_company_id"),
        "evaluation_criteria",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "campaigns",
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=False),
        sa.Column("competency_model_version_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("candidate_instructions", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("invitations_issued", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "competency_model_version_id"],
            [
                "competency_model_versions.company_id",
                "competency_model_versions.competency_model_version_id",
            ],
            name="fk_campaigns_competency_version",
        ),
        sa.ForeignKeyConstraint(
            ["company_id", "position_id"],
            ["positions.company_id", "positions.position_id"],
            name="fk_campaigns_position",
        ),
        sa.PrimaryKeyConstraint("campaign_id", name=op.f("pk_campaigns")),
        sa.UniqueConstraint(
            "company_id",
            "campaign_id",
            name="uq_campaigns_company_campaign",
        ),
    )
    op.create_index(
        op.f("ix_campaigns_company_id"),
        "campaigns",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "applicant_profiles",
        sa.Column("applicant_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("verification_method", sa.String(length=32), nullable=False),
        sa.Column("technology_tags", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("applicant_id", name=op.f("pk_applicant_profiles")),
        sa.UniqueConstraint(
            "company_id",
            "applicant_id",
            name="uq_applicant_profiles_company_applicant",
        ),
        sa.UniqueConstraint(
            "company_id",
            "invitation_id",
            name="uq_applicant_profiles_company_invitation",
        ),
    )
    op.create_index(
        op.f("ix_applicant_profiles_company_id"),
        "applicant_profiles",
        ["company_id"],
        unique=False,
    )
    op.create_table(
        "invitations",
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("campaign_id", sa.String(length=36), nullable=False),
        sa.Column("applicant_id", sa.String(length=36), nullable=False),
        sa.Column("applicant_email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("token_exchanged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("identity_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_transitions", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id", "campaign_id"],
            ["campaigns.company_id", "campaigns.campaign_id"],
            name="fk_invitations_campaign",
        ),
        sa.PrimaryKeyConstraint("invitation_id", name=op.f("pk_invitations")),
        sa.UniqueConstraint(
            "company_id",
            "invitation_id",
            name="uq_invitations_company_invitation",
        ),
        sa.UniqueConstraint("token_hash", name="uq_invitations_token_hash"),
    )
    op.create_index(
        op.f("ix_invitations_company_id"),
        "invitations",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_invitations_company_campaign",
        "invitations",
        ["company_id", "campaign_id"],
        unique=False,
    )
    op.create_table(
        "consent_records",
        sa.Column("consent_record_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("applicant_id", sa.String(length=36), nullable=False),
        sa.Column("policy_version", sa.String(length=128), nullable=False),
        sa.Column("purposes", sa.JSON(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_digest", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("consent_record_id", name=op.f("pk_consent_records")),
        sa.UniqueConstraint(
            "company_id",
            "consent_record_id",
            name="uq_consent_records_company_consent",
        ),
    )
    op.create_index(
        op.f("ix_consent_records_company_id"),
        "consent_records",
        ["company_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_consent_records_company_id"), table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_index("ix_invitations_company_campaign", table_name="invitations")
    op.drop_index(op.f("ix_invitations_company_id"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_index(op.f("ix_applicant_profiles_company_id"), table_name="applicant_profiles")
    op.drop_table("applicant_profiles")
    op.drop_index(op.f("ix_campaigns_company_id"), table_name="campaigns")
    op.drop_table("campaigns")
    op.drop_index(op.f("ix_evaluation_criteria_company_id"), table_name="evaluation_criteria")
    op.drop_table("evaluation_criteria")
    op.drop_index(
        op.f("ix_competency_model_versions_company_id"),
        table_name="competency_model_versions",
    )
    op.drop_table("competency_model_versions")
    op.drop_index(op.f("ix_positions_company_id"), table_name="positions")
    op.drop_table("positions")
    op.drop_index(op.f("ix_company_users_company_id"), table_name="company_users")
    op.drop_table("company_users")
    op.drop_table("companies")
