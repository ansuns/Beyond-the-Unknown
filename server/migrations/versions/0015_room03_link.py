"""Repair ROOM-03's canonical energy-to-door mechanism references."""

from alembic import op

revision = "0015_room03_link"
down_revision = "0014_room_combos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0007 created the door as MECH_ROOM03_DOOR_BARRIER; 0009 added the
    # canonical M03-DOOR-01 row but did not move objectives or linked references.
    op.execute(
        """
        UPDATE level_objectives
        SET mechanism_config_id = 'M03-DOOR-01'
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
        """
    )
    op.execute(
        """
        UPDATE mechanism_states AS canonical
        SET state = legacy.state || canonical.state,
            updated_at = GREATEST(legacy.updated_at, canonical.updated_at)
        FROM mechanism_states AS legacy
        JOIN level_runs AS runs ON runs.run_id = legacy.run_id
        WHERE runs.level_id = 'LV-ROOM-03'
          AND canonical.run_id = legacy.run_id
          AND canonical.player_id = legacy.player_id
          AND canonical.mechanism_config_id = 'M03-DOOR-01'
          AND legacy.mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
        """
    )
    op.execute(
        """
        DELETE FROM mechanism_states AS legacy
        USING level_runs AS runs
        WHERE runs.run_id = legacy.run_id
          AND runs.level_id = 'LV-ROOM-03'
          AND legacy.mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
          AND EXISTS (
              SELECT 1
              FROM mechanism_states AS canonical
              WHERE canonical.run_id = legacy.run_id
                AND canonical.player_id = legacy.player_id
                AND canonical.mechanism_config_id = 'M03-DOOR-01'
          )
        """
    )
    op.execute(
        """
        UPDATE mechanism_states AS state
        SET mechanism_config_id = 'M03-DOOR-01'
        FROM level_runs AS runs
        WHERE runs.run_id = state.run_id
          AND runs.level_id = 'LV-ROOM-03'
          AND state.mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET is_enabled = false
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
        """
    )
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
        SET is_enabled = true
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
        """
    )
    op.execute(
        """
        UPDATE level_objectives
        SET mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'M03-DOOR-01'
        """
    )
    op.execute(
        """
        UPDATE mechanism_states AS state
        SET mechanism_config_id = 'MECH_ROOM03_DOOR_BARRIER'
        FROM level_runs AS runs
        WHERE runs.run_id = state.run_id
          AND runs.level_id = 'LV-ROOM-03'
          AND state.mechanism_config_id = 'M03-DOOR-01'
        """
    )
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
