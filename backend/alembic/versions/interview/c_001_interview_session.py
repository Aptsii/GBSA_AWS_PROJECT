"""Create Lane C interview session persistence."""

import sqlalchemy as sa
from alembic import op

revision = "c_001"
down_revision = "c_000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("interview_session_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("invitation_id", sa.String(length=36), nullable=False),
        sa.Column("applicant_id", sa.String(length=36), nullable=False),
        sa.Column("interview_strategy_id", sa.String(length=36), nullable=False),
        sa.Column("competency_model_version_id", sa.String(length=36), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("session_sequence", sa.Integer(), nullable=False),
        sa.Column("row_version", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("degraded_modes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("session_sequence >= 0", name="session_sequence_nonnegative"),
        sa.CheckConstraint("row_version >= 1", name="session_row_version_positive"),
        sa.CheckConstraint(
            "state IN ('preparing', 'in_progress', 'awaiting_answer', "
            "'preparing_question', 'paused', 'completed', 'report_generating', 'reviewable')",
            name="interview_session_state",
        ),
        sa.PrimaryKeyConstraint("interview_session_id", name=op.f("pk_interview_sessions")),
        sa.UniqueConstraint(
            "company_id",
            "interview_session_id",
            name="uq_interview_sessions_company_session",
        ),
    )
    op.create_index(op.f("ix_interview_sessions_company_id"), "interview_sessions", ["company_id"])
    op.create_index(
        op.f("ix_interview_sessions_invitation_id"),
        "interview_sessions",
        ["invitation_id"],
    )
    op.create_index(
        op.f("ix_interview_sessions_applicant_id"), "interview_sessions", ["applicant_id"]
    )

    op.create_table(
        "interview_turns",
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("interview_session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("target_criterion_id", sa.String(length=36), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("model_config_version", sa.String(length=128), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="interview_turn_sequence_positive"),
        sa.CheckConstraint(
            "speaker IN ('interviewer', 'applicant')", name="interview_turn_speaker"
        ),
        sa.CheckConstraint(
            "status IN ('preparing', 'presented', 'recording', 'final', 'failed')",
            name="interview_turn_status",
        ),
        sa.CheckConstraint(
            "status != 'final' OR (text IS NOT NULL AND finalized_at IS NOT NULL)",
            name="final_interview_turn_has_text_and_time",
        ),
        sa.CheckConstraint(
            "speaker != 'interviewer' OR target_criterion_id IS NOT NULL",
            name="interviewer_turn_has_criterion",
        ),
        sa.PrimaryKeyConstraint("turn_id", name=op.f("pk_interview_turns")),
        sa.UniqueConstraint(
            "company_id",
            "interview_session_id",
            "sequence",
            name="uq_interview_turn_session_sequence",
        ),
        sa.UniqueConstraint(
            "company_id",
            "interview_session_id",
            "idempotency_key",
            name="uq_interview_turn_session_idempotency",
        ),
    )
    op.create_index(op.f("ix_interview_turns_company_id"), "interview_turns", ["company_id"])
    op.create_index(
        op.f("ix_interview_turns_interview_session_id"),
        "interview_turns",
        ["interview_session_id"],
    )

    op.create_table(
        "session_checkpoints",
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("interview_session_id", sa.String(length=36), nullable=False),
        sa.Column("session_sequence", sa.Integer(), nullable=False),
        sa.Column("last_final_turn_id", sa.String(length=36), nullable=True),
        sa.Column("last_media_chunk_sequence", sa.Integer(), nullable=False),
        sa.Column("pending_turn_id", sa.String(length=36), nullable=True),
        sa.Column("hot_view_sync_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("session_sequence >= 0", name="checkpoint_sequence_nonnegative"),
        sa.CheckConstraint(
            "last_media_chunk_sequence >= 0", name="checkpoint_media_sequence_nonnegative"
        ),
        sa.CheckConstraint(
            "hot_view_sync_status IN ('pending', 'synced', 'degraded')",
            name="checkpoint_hot_view_status",
        ),
        sa.PrimaryKeyConstraint("checkpoint_id", name=op.f("pk_session_checkpoints")),
        sa.UniqueConstraint(
            "company_id",
            "interview_session_id",
            "session_sequence",
            name="uq_checkpoint_session_sequence",
        ),
    )
    op.create_index(
        op.f("ix_session_checkpoints_company_id"), "session_checkpoints", ["company_id"]
    )
    op.create_index(
        op.f("ix_session_checkpoints_interview_session_id"),
        "session_checkpoints",
        ["interview_session_id"],
    )

    op.create_table(
        "recording_chunks",
        sa.Column("recording_chunk_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("interview_session_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("session_start_ms", sa.Integer(), nullable=False),
        sa.Column("session_end_ms", sa.Integer(), nullable=False),
        sa.Column("upload_status", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sequence >= 0", name="recording_chunk_sequence_nonnegative"),
        sa.CheckConstraint("byte_size >= 1", name="recording_chunk_byte_size_positive"),
        sa.CheckConstraint(
            "session_start_ms >= 0 AND session_end_ms > session_start_ms",
            name="recording_chunk_time_range",
        ),
        sa.CheckConstraint(
            "upload_status IN ('issued', 'uploaded', 'verified', 'failed')",
            name="recording_chunk_upload_status",
        ),
        sa.PrimaryKeyConstraint("recording_chunk_id", name=op.f("pk_recording_chunks")),
        sa.UniqueConstraint(
            "company_id",
            "interview_session_id",
            "sequence",
            name="uq_recording_chunk_session_sequence",
        ),
        sa.UniqueConstraint(
            "company_id",
            "interview_session_id",
            "idempotency_key",
            name="uq_recording_chunk_session_idempotency",
        ),
    )
    op.create_index(op.f("ix_recording_chunks_company_id"), "recording_chunks", ["company_id"])
    op.create_index(
        op.f("ix_recording_chunks_interview_session_id"),
        "recording_chunks",
        ["interview_session_id"],
    )


def downgrade() -> None:
    op.drop_table("recording_chunks")
    op.drop_table("session_checkpoints")
    op.drop_table("interview_turns")
    op.drop_table("interview_sessions")
