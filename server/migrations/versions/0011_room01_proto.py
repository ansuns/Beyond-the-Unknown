"""Enable the first room's explicitly provisional playable prototype."""

import sqlalchemy as sa
from alembic import op

revision = "0011_room01_proto"
down_revision = "0010_mech_id_complete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "level_run_positions",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("run_id", "player_id"),
        sa.ForeignKeyConstraint(
            ["run_id", "player_id"],
            ["level_runs.run_id", "level_runs.player_id"],
            ondelete="CASCADE",
            name="fk_level_run_position_owner",
        ),
        sa.CheckConstraint("x BETWEEN 0 AND 12", name="ck_level_run_position_x"),
        sa.CheckConstraint("y BETWEEN 0 AND 8", name="ck_level_run_position_y"),
    )
    op.create_table(
        "mechanism_interaction_events",
        sa.Column(
            "event_id",
            sa.Uuid(),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("mechanism_id", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", sa.dialects.postgresql.JSONB(), nullable=False),
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
            name="fk_mechanism_interaction_run_owner",
        ),
        sa.UniqueConstraint(
            "run_id",
            "player_id",
            "idempotency_key",
            name="uq_mechanism_interaction_idempotency",
        ),
    )

    # These values are a playable prototype baseline, not final production tuning.
    # The level config and mechanism configs explicitly retain PROTOTYPE status.
    op.execute(
        """
        UPDATE levels
        SET config = config || jsonb_build_object(
            'content_status', 'PROTOTYPE_TUNING_PENDING',
            'prototype_bounds', jsonb_build_object('min_x', 0, 'max_x', 12, 'min_y', 0, 'max_y', 8),
            'prototype_spawn', jsonb_build_object('x', 1, 'y', 4),
            'prototype_controls', jsonb_build_object('movement_speed', 3.0, 'interaction_radius', 1.5)
        )
        WHERE level_id = 'LV-ROOM-01'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET position_x = CASE mechanism_config_id
                WHEN 'M01-HIDEABLE-01' THEN 5.0
                WHEN 'M01-LIGHT-01' THEN 7.5
                WHEN 'M01-EXIT-01' THEN 10.5
            END,
            position_y = 4.0,
            config = config || CASE mechanism_config_id
                WHEN 'M01-HIDEABLE-01' THEN
                    jsonb_build_object('content_status', 'PROTOTYPE_TUNING_PENDING')
                WHEN 'M01-LIGHT-01' THEN
                    jsonb_build_object('content_status', 'PROTOTYPE_TUNING_PENDING')
                WHEN 'M01-EXIT-01' THEN
                    jsonb_build_object(
                        'content_status', 'PROTOTYPE_TUNING_PENDING',
                        'interaction_radius', 1.5,
                        'requires_visible_mechanism_id', 'M01-HIDEABLE-01'
                    )
            END
        WHERE level_id = 'LV-ROOM-01'
          AND mechanism_config_id IN ('M01-HIDEABLE-01','M01-LIGHT-01','M01-EXIT-01')
        """
    )
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = 1200,
            radius = 2.0,
            config_status = 'READY'
        WHERE rule_id = 'RULE_ECHO'
        """
    )
    op.execute(
        """
        UPDATE level_objectives
        SET config_status = 'READY'
        WHERE level_id = 'LV-ROOM-01'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = NULL, radius = NULL, config_status = 'TUNING_REQUIRED'
        WHERE rule_id = 'RULE_ECHO'
        """
    )
    op.execute(
        """
        UPDATE level_objectives
        SET config_status = 'CONTENT_PENDING'
        WHERE level_id = 'LV-ROOM-01'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET position_x = NULL, position_y = NULL,
            config = config - 'content_status' - 'interaction_radius'
                    - 'requires_visible_mechanism_id'
        WHERE level_id = 'LV-ROOM-01'
          AND mechanism_config_id IN ('M01-HIDEABLE-01','M01-LIGHT-01','M01-EXIT-01')
        """
    )
    op.execute(
        """
        UPDATE levels
        SET config = config - 'content_status' - 'prototype_bounds'
                      - 'prototype_spawn' - 'prototype_controls'
        WHERE level_id = 'LV-ROOM-01'
        """
    )
    op.drop_table("mechanism_interaction_events")
    op.drop_table("level_run_positions")
