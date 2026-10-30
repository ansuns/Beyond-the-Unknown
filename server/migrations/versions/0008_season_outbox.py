import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0008_season_outbox"
down_revision = "0007_progress_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "seasons",
        sa.Column("review_until_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "seasons",
        sa.Column("reviewed_at_utc", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "seasons",
        sa.Column("reviewed_by", sa.String(96), nullable=True),
    )
    op.add_column(
        "seasons",
        sa.Column("review_note", sa.String(512), nullable=True),
    )

    op.create_table(
        "task_outbox",
        sa.Column(
            "task_id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", JSONB(), nullable=False, server_default="{}"),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("published_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column(
            "created_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING','PUBLISHED','COMPLETED','FAILED')",
            name="ck_task_outbox_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_task_outbox_attempts"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 20", name="ck_task_outbox_max_attempts"),
    )
    op.create_index(
        "idx_task_outbox_due",
        "task_outbox",
        ["status", "available_at_utc", "created_at_utc"],
    )

    op.create_table(
        "worker_task_receipts",
        sa.Column("task_id", sa.Uuid(), primary_key=True),
        sa.Column("task_type", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column(
            "processed_at_utc",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("worker_task_receipts")
    op.drop_index("idx_task_outbox_due", table_name="task_outbox")
    op.drop_table("task_outbox")
    op.drop_column("seasons", "review_note")
    op.drop_column("seasons", "reviewed_by")
    op.drop_column("seasons", "reviewed_at_utc")
    op.drop_column("seasons", "review_until_utc")
