"""Make prototype bounds, spawn and movement controls available for every level."""

from alembic import op

revision = "0016_proto_layout"
down_revision = "0015_room03_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        UPDATE levels
        SET config = config || jsonb_build_object(
            'content_status', 'PROTOTYPE_TUNING_PENDING',
            'prototype_bounds', jsonb_build_object(
                'min_x', 0, 'max_x', 12, 'min_y', 0, 'max_y', 8
            ),
            'prototype_spawn', jsonb_build_object('x', 1, 'y', 4),
            'prototype_controls',
                COALESCE(config->'prototype_controls', '{}'::jsonb)
                || jsonb_build_object(
                    'movement_speed', 3.0,
                    'interaction_radius', 1.5,
                    'position_sync_interval_ms', 120
                )
        )
        WHERE level_id IN (
            'LV-ROOM-01', 'LV-ROOM-02', 'LV-ROOM-03',
            'LV-ROOM-04', 'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        UPDATE levels
        SET config = jsonb_set(
            config,
            '{prototype_controls}',
            (COALESCE(config->'prototype_controls', '{}'::jsonb)
                - 'position_sync_interval_ms'),
            true
        )
        WHERE level_id IN (
            'LV-ROOM-01', 'LV-ROOM-02', 'LV-ROOM-03',
            'LV-ROOM-04', 'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )
