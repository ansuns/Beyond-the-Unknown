"""Align persisted mechanism catalog IDs with the canonical GDD level data.

The GDD level catalog is the source of truth for mechanism identifiers. This
migration renames the early placeholder IDs and inserts mechanisms that were
present in the GDD but absent from the original server seed catalog. Spatial
positions and tuning remain intentionally unset until content approval.
"""

from alembic import op

revision = "0009_gdd_mechanism_ids"
down_revision = "0008_season_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep historical per-run state rows aligned with the canonical GDD IDs.
    op.execute(
        """
        UPDATE mechanism_states
        SET mechanism_config_id = CASE mechanism_config_id
            WHEN 'MECH-ROOM01-HIDDEN-01' THEN 'M01-HIDEABLE-01'
            WHEN 'MECH_BRIDGE' THEN 'M02-BRIDGE-01'
            WHEN 'MECH_ENERGY_GATE' THEN 'M03-ENERGY-01'
            WHEN 'MECH_MOVING_PLATFORM' THEN 'M04-PLATFORM-01'
        END
        WHERE mechanism_config_id IN (
            'MECH-ROOM01-HIDDEN-01', 'MECH_BRIDGE',
            'MECH_ENERGY_GATE', 'MECH_MOVING_PLATFORM'
        )
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_config_id = CASE mechanism_config_id
            WHEN 'MECH-ROOM01-HIDDEN-01' THEN 'M01-HIDEABLE-01'
            WHEN 'MECH_BRIDGE' THEN 'M02-BRIDGE-01'
            WHEN 'MECH_ENERGY_GATE' THEN 'M03-ENERGY-01'
            WHEN 'MECH_MOVING_PLATFORM' THEN 'M04-PLATFORM-01'
        END
        WHERE mechanism_config_id IN (
            'MECH-ROOM01-HIDDEN-01', 'MECH_BRIDGE',
            'MECH_ENERGY_GATE', 'MECH_MOVING_PLATFORM'
        )
        """
    )

    # Fill the gaps between the GDD's six-level catalog and the original
    # server seed. These rows are deliberately disabled from gameplay by
    # missing positions / TUNING_REQUIRED configuration, not silently guessed.
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
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_config_id = CASE mechanism_config_id
            WHEN 'M01-HIDEABLE-01' THEN 'MECH-ROOM01-HIDDEN-01'
            WHEN 'M02-BRIDGE-01' THEN 'MECH_BRIDGE'
            WHEN 'M03-ENERGY-01' THEN 'MECH_ENERGY_GATE'
            WHEN 'M04-PLATFORM-01' THEN 'MECH_MOVING_PLATFORM'
        END
        WHERE mechanism_config_id IN (
            'M01-HIDEABLE-01', 'M02-BRIDGE-01',
            'M03-ENERGY-01', 'M04-PLATFORM-01'
        )
    )
    op.execute(
        """
        UPDATE mechanism_states
        SET mechanism_config_id = CASE mechanism_config_id
            WHEN 'M01-HIDEABLE-01' THEN 'MECH-ROOM01-HIDDEN-01'
            WHEN 'M02-BRIDGE-01' THEN 'MECH_BRIDGE'
            WHEN 'M03-ENERGY-01' THEN 'MECH_ENERGY_GATE'
            WHEN 'M04-PLATFORM-01' THEN 'MECH_MOVING_PLATFORM'
        END
        WHERE mechanism_config_id IN (
            'M01-HIDEABLE-01', 'M02-BRIDGE-01',
            'M03-ENERGY-01', 'M04-PLATFORM-01'
        )
        """
    )
