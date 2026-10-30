import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_authoritative_law_actions"
down_revision = "0006_mech_catalog_align"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "law_action_events",
        sa.Column(
            "event_id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("mechanism_config_id", sa.String(100), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("combo_id", sa.String(64), nullable=True),
        sa.Column(
            "result",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "player_id"],
            ["level_runs.run_id", "level_runs.player_id"],
            ondelete="CASCADE",
            name="fk_law_action_run_owner",
        ),
        sa.UniqueConstraint("run_id", "idempotency_key", name="uq_law_action_run_idempotency"),
        sa.CheckConstraint("action IN ('APPLY','RELEASE')", name="ck_law_action_type"),
        sa.CheckConstraint(
            "rule_id IN ('RULE_ECHO','RULE_GAZE','RULE_REVERSE')",
            name="ck_law_action_rule",
        ),
    )
    op.create_index(
        "idx_law_action_run_target_time",
        "law_action_events",
        ["run_id", "mechanism_config_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_law_action_run_target_time", table_name="law_action_events")
    op.drop_table("law_action_events")
