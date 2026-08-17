"""Scope reporting human-review idempotency by company."""

from alembic import op

revision = "m_003"
down_revision = "m_002"
branch_labels = None
depends_on = None

data_migration_note = (
    "The existing global unique constraint is replaced without deleting or rewriting rows. "
    "Existing globally unique idempotency keys already satisfy the new tenant-scoped constraint."
)


def upgrade() -> None:
    with op.batch_alter_table("human_reviews") as batch_op:
        batch_op.drop_constraint(
            "uq_human_reviews_idempotency_key",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_human_reviews_company_id_idempotency_key",
            ["company_id", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("human_reviews") as batch_op:
        batch_op.drop_constraint(
            "uq_human_reviews_company_id_idempotency_key",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_human_reviews_idempotency_key",
            ["idempotency_key"],
        )
