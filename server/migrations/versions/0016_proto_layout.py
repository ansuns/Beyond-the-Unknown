"""Add the prototype position sync interval to existing level controls."""

from alembic import op

revision = "0016_proto_layout"
down_revision = "0015_room03_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0011 and 0013 already own bounds, spawn, speed and interaction radius.
    # This migration adds only the new sync interval and preserves tuned values.
    op.get_bind().exec_driver_sql(
        """
        UPDATE levels
        SET config = jsonb_set(
            config,
            '{prototype_controls}',
            COALESCE(config->'prototype_controls', '{}'::jsonb)
                || jsonb_build_object('position_sync_interval_ms', 120),
            true
        )
        WHERE level_id IN (
            'LV-ROOM-01', 'LV-ROOM-02', 'LV-ROOM-03',
            'LV-ROOM-04', 'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )


def downgrade() -> None:
    # Revert only the field introduced here. Earlier migrations own all other
    # prototype layout keys, so removing them here would corrupt their state.
    op.get_bind().exec_driver_sql(
        """
        UPDATE levels
        SET config = jsonb_set(
            config,
            '{prototype_controls}',
            COALESCE(config->'prototype_controls', '{}'::jsonb)
                - 'position_sync_interval_ms',
            true
        )
        WHERE level_id IN (
            'LV-ROOM-01', 'LV-ROOM-02', 'LV-ROOM-03',
            'LV-ROOM-04', 'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )
