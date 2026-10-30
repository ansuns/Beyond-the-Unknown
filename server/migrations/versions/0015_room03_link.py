"""Repair ROOM-03's canonical energy-to-door mechanism link."""

from alembic import op

revision = "0015_room03_link"
down_revision = "0014_room_combos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The legacy ROOM-03 config retained MECH_ROOM03_DOOR_BARRIER after the
    # catalog row was renamed to M03-DOOR-01 by the canonical ID migration.
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET config = config || jsonb_build_object(
            'linked_mechanism_id', 'M03-DOOR-01'
        )
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'M03-ENERGY-01'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET config = config || jsonb_build_object(
            'linked_mechanism_id', 'MECH_ROOM03_DOOR_BARRIER'
        )
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'M03-ENERGY-01'
        """
    )
