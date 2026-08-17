"""Add Integration-owned durable messaging and audit tables."""

import sqlalchemy as sa
from alembic import op

revision = "m_002"
down_revision = "m_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("aggregate_type", sa.String(length=128), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("causation_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_failure_code", sa.String(length=128), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("company_id", "event_id"),
        sa.UniqueConstraint("company_id", "idempotency_key"),
    )
    op.create_table(
        "processed_messages",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("consumer_name", sa.String(length=128), nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("first_processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_digest", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint(
            "company_id",
            "consumer_name",
            "event_id",
            "event_version",
        ),
        sa.UniqueConstraint(
            "company_id",
            "consumer_name",
            "event_id",
            "event_version",
            name="uq_processed_messages_event",
        ),
        sa.UniqueConstraint(
            "company_id",
            "consumer_name",
            "idempotency_key",
            name="uq_processed_messages_idempotency",
        ),
    )
    op.create_table(
        "audit_events",
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("audit_event_id", sa.String(length=36), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=128), nullable=False),
        sa.Column("resource_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=128), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("command_digest", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("company_id", "audit_event_id"),
        sa.UniqueConstraint("company_id", "idempotency_key"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("processed_messages")
    op.drop_table("outbox_events")
