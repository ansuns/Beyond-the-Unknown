import sqlalchemy as sa

from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0008_transactional_outbox"
down_revision = "0007_progress_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column(
            "event_id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint("attempts >= 0", name="ck_outbox_events_attempts_nonnegative"),
    )
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["next_attempt_at", "created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )
    op.create_table(
        "processed_task_messages",
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("task_id", sa.String(100), nullable=False),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("processed_task_messages")
    op.drop_index("ix_outbox_events_pending", table_name="outbox_events")
    op.drop_table("outbox_events")
