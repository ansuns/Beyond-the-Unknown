"""Align persisted mechanism catalog IDs with the canonical GDD level data."""

from alembic import op

revision = "0009_gdd_mechanism_ids"
down_revision = "0008_season_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Rename legacy IDs and add catalog entries missing from the GDD mapping."""
    id_map = {
        "MECH-ROOM01-HIDDEN-01": "M01-HIDEABLE-01",
        "MECH_BRIDGE": "M02-BRIDGE-01",
        "MECH_ENERGY_GATE": "M03-ENERGY-01",
        "MECH_MOVING_PLATFORM": "M04-PLATFORM-01",
    }
    for old_id, new_id in id_map.items():
        op.execute(
            """
            UPDATE level_mechanism_catalog
            SET mechanism_config_id = :new_id
            WHERE mechanism_config_id = :old_id
            """,
            {"old_id": old_id, "new_id": new_id},
        )
        op.execute(
            """
            UPDATE mechanism_states
            SET mechanism_config_id = :new_id
            WHERE mechanism_config_id = :old_id
            """,
            {"old_id": old_id, "new_id": new_id},
        )

    # Catalog entries exist for discovery and future content work, but remain
    # non-interactive until positions, art and rule tuning are approved.
    op.execute(
        """
        INSERT INTO level_mechanism_catalog
            (level_id, mechanism_config_id, mechanism_type, target_type,
             initial_state, target_state, trigger_rule, config, is_enabled)
        VALUES
            ('LV-ROOM-03', 'M03-DOOR-01', 'DOOR_BARRIER', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["COMBO_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART"}'::jsonb, true),
            ('LV-ROOM-04', 'M04-PLATFORM-02', 'PLATFORM_BRIDGE', 'PLATFORM',
             'INACTIVE', 'TRIGGERED', '["COMBO_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART"}'::jsonb, true),
            ('LV-HIDDEN-01', 'H01-GATE', 'HIDDEN_GATE', 'MECHANISM',
             'LOCKED', 'TRIGGERED', '["LEVEL_EVENT"]'::jsonb,
             '{"config_status":"PENDING_HIDDEN_ROUTE"}'::jsonb, true),
            ('LV-HIDDEN-01', 'H01-END', 'ENDING_CORE', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["PLAYER_INTERACT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART"}'::jsonb, true)
        ON CONFLICT (level_id, mechanism_config_id) DO NOTHING
        """
    )


def downgrade() -> None:
    """Remove only rows introduced here and restore legacy catalog identifiers."""
    op.execute(
        """
        DELETE FROM level_mechanism_catalog
        WHERE (level_id, mechanism_config_id) IN (
            ('LV-ROOM-03', 'M03-DOOR-01'),
            ('LV-ROOM-04', 'M04-PLATFORM-02'),
            ('LV-HIDDEN-01', 'H01-GATE'),
            ('LV-HIDDEN-01', 'H01-END')
        )
        """
    )
    reverse_map = {
        "M01-HIDEABLE-01": "MECH-ROOM01-HIDDEN-01",
        "M02-BRIDGE-01": "MECH_BRIDGE",
        "M03-ENERGY-01": "MECH_ENERGY_GATE",
        "M04-PLATFORM-01": "MECH_MOVING_PLATFORM",
    }
    for new_id, old_id in reverse_map.items():
        op.execute(
            """
            UPDATE level_mechanism_catalog
            SET mechanism_config_id = :old_id
            WHERE mechanism_config_id = :new_id
            """,
            {"old_id": old_id, "new_id": new_id},
        )
        op.execute(
            """
            UPDATE mechanism_states
            SET mechanism_config_id = :old_id
            WHERE mechanism_config_id = :new_id
            """,
            {"old_id": old_id, "new_id": new_id},
        )
