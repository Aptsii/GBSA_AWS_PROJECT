"""Create submission analysis, source, Git, and strategy tables."""

from alembic import op
import sqlalchemy as sa

revision = "b_001"
down_revision = "b_000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "submissions",
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("applicant_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_uri", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("byte_size", sa.Integer(), nullable=True),
        sa.Column("media_type", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("impact_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("submission_id", name=op.f("pk_submissions")),
        sa.UniqueConstraint("company_id", "submission_id", name="uq_submissions_company_submission"),
    )
    for column in ("company_id", "invitation_id", "applicant_id"):
        op.create_index(op.f(f"ix_submissions_{column}"), "submissions", [column], unique=False)

    op.create_table(
        "submission_analyses",
        sa.Column("analysis_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("analysis_version", sa.Integer(), nullable=False),
        sa.Column("extractor_version", sa.String(length=128), nullable=False),
        sa.Column("chunk_config_version", sa.String(length=128), nullable=False),
        sa.Column("claims", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False),
        sa.Column("verification_points", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("analysis_id", name=op.f("pk_submission_analyses")),
        sa.UniqueConstraint(
            "company_id", "submission_id", "analysis_version", name="uq_submission_analysis_version"
        ),
    )
    op.create_index(op.f("ix_submission_analyses_company_id"), "submission_analyses", ["company_id"])
    op.create_index(op.f("ix_submission_analyses_submission_id"), "submission_analyses", ["submission_id"])

    op.create_table(
        "submission_source_references",
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("applicant_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_version", sa.Integer(), nullable=False),
        sa.Column("source_location", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("ownership_confidence", sa.Float(), nullable=True),
        sa.Column("evidence_eligible", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("source_id", name=op.f("pk_submission_source_references")),
    )
    for column in ("company_id", "invitation_id", "applicant_id", "submission_id"):
        op.create_index(
            op.f(f"ix_submission_source_references_{column}"),
            "submission_source_references",
            [column],
        )

    op.create_table(
        "git_repository_analyses",
        sa.Column("repository_analysis_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("submission_id", sa.String(length=36), nullable=False),
        sa.Column("repository_url", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=False),
        sa.Column("pinned_head_sha", sa.String(length=40), nullable=False),
        sa.Column("candidate_identity_inputs", sa.JSON(), nullable=False),
        sa.Column("limits_applied", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("repository_analysis_id", name=op.f("pk_git_repository_analyses")),
    )
    op.create_index(op.f("ix_git_repository_analyses_company_id"), "git_repository_analyses", ["company_id"])
    op.create_index(op.f("ix_git_repository_analyses_submission_id"), "git_repository_analyses", ["submission_id"])

    op.create_table(
        "git_commit_analyses",
        sa.Column("git_commit_analysis_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("repository_analysis_id", sa.String(length=36), nullable=False),
        sa.Column("parent_sha", sa.String(length=40), nullable=False),
        sa.Column("commit_sha", sa.String(length=40), nullable=False),
        sa.Column("author_match_inputs", sa.JSON(), nullable=False),
        sa.Column("change_summary_object_id", sa.String(length=36), nullable=False),
        sa.Column("ownership_confidence", sa.Float(), nullable=False),
        sa.Column("ownership_class", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("git_commit_analysis_id", name=op.f("pk_git_commit_analyses")),
    )
    op.create_index(op.f("ix_git_commit_analyses_company_id"), "git_commit_analyses", ["company_id"])
    op.create_index(op.f("ix_git_commit_analyses_repository_analysis_id"), "git_commit_analyses", ["repository_analysis_id"])

    op.create_table(
        "candidate_code_units",
        sa.Column("code_unit_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("git_commit_analysis_id", sa.String(length=36), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("original_line_range", sa.JSON(), nullable=False),
        sa.Column("current_line_range", sa.JSON(), nullable=False),
        sa.Column("candidate_owned_regions", sa.JSON(), nullable=False),
        sa.Column("related_test_ids", sa.JSON(), nullable=False),
        sa.Column("dependency_ids", sa.JSON(), nullable=False),
        sa.Column("index_document_ids", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("code_unit_id", name=op.f("pk_candidate_code_units")),
    )
    op.create_index(op.f("ix_candidate_code_units_company_id"), "candidate_code_units", ["company_id"])
    op.create_index(op.f("ix_candidate_code_units_git_commit_analysis_id"), "candidate_code_units", ["git_commit_analysis_id"])

    op.create_table(
        "interview_strategies",
        sa.Column("interview_strategy_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("competency_model_version_id", sa.String(length=36), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("common_topics", sa.JSON(), nullable=False),
        sa.Column("verification_points", sa.JSON(), nullable=False),
        sa.Column("follow_up_directions", sa.JSON(), nullable=False),
        sa.Column("time_budget", sa.JSON(), nullable=False),
        sa.Column("required_evidence_plan", sa.JSON(), nullable=False),
        sa.Column("source_reference_candidates", sa.JSON(), nullable=False),
        sa.Column("model_config_version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("interview_strategy_id", name=op.f("pk_interview_strategies")),
        sa.UniqueConstraint(
            "company_id", "invitation_id", "strategy_version", name="uq_strategy_invitation_version"
        ),
    )
    op.create_index(op.f("ix_interview_strategies_company_id"), "interview_strategies", ["company_id"])
    op.create_index(op.f("ix_interview_strategies_invitation_id"), "interview_strategies", ["invitation_id"])


def downgrade() -> None:
    op.drop_table("interview_strategies")
    op.drop_table("candidate_code_units")
    op.drop_table("git_commit_analyses")
    op.drop_table("git_repository_analyses")
    op.drop_table("submission_source_references")
    op.drop_table("submission_analyses")
    op.drop_table("submissions")
