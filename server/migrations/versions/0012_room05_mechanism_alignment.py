"""Align ROOM-05 objectives and hidden-route sequence with its canonical M05 mechanisms."""

from alembic import op

revision = "0012_room05_mechanism_alignment"
down_revision = "0011_room01_proto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ROOM-05 owns its own mechanism instances. The old progress seed reused
    # ROOM-02/03/04 IDs, while the canonical level config and client use M05 IDs.
    op.execute(
        """
        UPDATE level_objectives
        SET mechanism_config_id = CASE mechanism_config_id
            WHEN 'M02-BRIDGE-01' THEN 'M05-BRIDGE-01'
            WHEN 'M03-ENERGY-01' THEN 'M05-ENERGY-01'
            WHEN 'M04-PLATFORM-01' THEN 'M05-REVERSE-01'
        END
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id IN (
              'M02-BRIDGE-01', 'M03-ENERGY-01', 'M04-PLATFORM-01'
          )
        """
    )

    # Merge any historical duplicate state into the canonical M05 state before
    # removing the legacy per-room aliases. Canonical state wins on key overlap.
    op.execute(
        """
        UPDATE mechanism_states AS canonical
        SET state = legacy.state || canonical.state,
            updated_at = GREATEST(legacy.updated_at, canonical.updated_at)
        FROM mechanism_states AS legacy
        JOIN level_runs AS runs ON runs.run_id = legacy.run_id
        WHERE runs.level_id = 'LV-ROOM-05'
          AND canonical.run_id = legacy.run_id
          AND canonical.player_id = legacy.player_id
          AND (
              (legacy.mechanism_config_id = 'M02-BRIDGE-01'
               AND canonical.mechanism_config_id = 'M05-BRIDGE-01')
           OR (legacy.mechanism_config_id = 'M03-ENERGY-01'
               AND canonical.mechanism_config_id = 'M05-ENERGY-01')
           OR (legacy.mechanism_config_id = 'M04-PLATFORM-01'
               AND canonical.mechanism_config_id = 'M05-REVERSE-01')
          )
        """
    )
    op.execute(
        """
        DELETE FROM mechanism_states AS legacy
        USING level_runs AS runs
        WHERE runs.run_id = legacy.run_id
          AND runs.level_id = 'LV-ROOM-05'
          AND (
              (legacy.mechanism_config_id = 'M02-BRIDGE-01'
               AND EXISTS (
                   SELECT 1 FROM mechanism_states canonical
                   WHERE canonical.run_id = legacy.run_id
                     AND canonical.player_id = legacy.player_id
                     AND canonical.mechanism_config_id = 'M05-BRIDGE-01'
               ))
           OR (legacy.mechanism_config_id = 'M03-ENERGY-01'
               AND EXISTS (
                   SELECT 1 FROM mechanism_states canonical
                   WHERE canonical.run_id = legacy.run_id
                     AND canonical.player_id = legacy.player_id
                     AND canonical.mechanism_config_id = 'M05-ENERGY-01'
               ))
           OR (legacy.mechanism_config_id = 'M04-PLATFORM-01'
               AND EXISTS (
                   SELECT 1 FROM mechanism_states canonical
                   WHERE canonical.run_id = legacy.run_id
                     AND canonical.player_id = legacy.player_id
                     AND canonical.mechanism_config_id = 'M05-REVERSE-01'
               ))
          )
        """
    )
    op.execute(
        """
        UPDATE mechanism_states AS state
        SET mechanism_config_id = CASE state.mechanism_config_id
            WHEN 'M02-BRIDGE-01' THEN 'M05-BRIDGE-01'
            WHEN 'M03-ENERGY-01' THEN 'M05-ENERGY-01'
            WHEN 'M04-PLATFORM-01' THEN 'M05-REVERSE-01'
        END
        FROM level_runs AS runs
        WHERE runs.run_id = state.run_id
          AND runs.level_id = 'LV-ROOM-05'
          AND state.mechanism_config_id IN (
              'M02-BRIDGE-01', 'M03-ENERGY-01', 'M04-PLATFORM-01'
          )
        """
    )

    # Preserve historical combo events so the route remains unlockable for
    # players who completed ROOM-05 before this correction.
    op.execute(
        """
        UPDATE rule_cast_events AS events
        SET target_id = CASE events.target_id
            WHEN 'M02-BRIDGE-01' THEN 'M05-BRIDGE-01'
            WHEN 'M03-ENERGY-01' THEN 'M05-ENERGY-01'
            WHEN 'M04-PLATFORM-01' THEN 'M05-REVERSE-01'
            ELSE events.target_id
        END,
        result = CASE
            WHEN events.result #>> '{combo,mechanism_id}' IS NULL THEN events.result
            ELSE jsonb_set(
                events.result,
                '{combo,mechanism_id}',
                to_jsonb(CASE events.result #>> '{combo,mechanism_id}'
                    WHEN 'M02-BRIDGE-01' THEN 'M05-BRIDGE-01'
                    WHEN 'M03-ENERGY-01' THEN 'M05-ENERGY-01'
                    WHEN 'M04-PLATFORM-01' THEN 'M05-REVERSE-01'
                    ELSE events.result #>> '{combo,mechanism_id}'
                END),
                true
            )
        END
        FROM level_runs AS runs
        WHERE runs.run_id = events.run_id
          AND runs.level_id = 'LV-ROOM-05'
    """
    )
    op.execute(
        """
        UPDATE player_rule_states AS state
        SET active_target_id = CASE state.active_target_id
            WHEN 'M02-BRIDGE-01' THEN 'M05-BRIDGE-01'
            WHEN 'M03-ENERGY-01' THEN 'M05-ENERGY-01'
            WHEN 'M04-PLATFORM-01' THEN 'M05-REVERSE-01'
        END
        FROM level_runs AS runs
        WHERE runs.run_id = state.run_id
          AND runs.level_id = 'LV-ROOM-05'
          AND state.active_target_id IN (
              'M02-BRIDGE-01', 'M03-ENERGY-01', 'M04-PLATFORM-01'
          )
        """
    )

    # Disable duplicate legacy catalog entries; the canonical M05 entries
    # remain enabled and are the only targets used by ROOM-05 objectives.
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET is_enabled = false
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id IN (
              'M02-BRIDGE-01', 'M03-ENERGY-01', 'M04-PLATFORM-01'
          )
        """
    )
    op.execute(
        """
        UPDATE hidden_routes
        SET trigger_mechanism_sequence =
            '["M05-BRIDGE-01","M05-ENERGY-01","M05-REVERSE-01"]'::jsonb
        WHERE hidden_route_id = 'HIDDEN-ROUTE-01'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET is_enabled = true
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id IN (
              'M02-BRIDGE-01', 'M03-ENERGY-01', 'M04-PLATFORM-01'
          )
        """
    )
    op.execute(
        """
        UPDATE hidden_routes
        SET trigger_mechanism_sequence =
            '["M02-BRIDGE-01","M03-ENERGY-01","M04-PLATFORM-01"]'::jsonb
        WHERE hidden_route_id = 'HIDDEN-ROUTE-01'
        """
    )
    op.execute(
        """
        UPDATE level_objectives
        SET mechanism_config_id = CASE mechanism_config_id
            WHEN 'M05-BRIDGE-01' THEN 'M02-BRIDGE-01'
            WHEN 'M05-ENERGY-01' THEN 'M03-ENERGY-01'
            WHEN 'M05-REVERSE-01' THEN 'M04-PLATFORM-01'
        END
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id IN (
              'M05-BRIDGE-01', 'M05-ENERGY-01', 'M05-REVERSE-01'
          )
        """
    )

    op.execute(
        """
        UPDATE mechanism_states AS state
        SET mechanism_config_id = CASE state.mechanism_config_id
            WHEN 'M05-BRIDGE-01' THEN 'M02-BRIDGE-01'
            WHEN 'M05-ENERGY-01' THEN 'M03-ENERGY-01'
            WHEN 'M05-REVERSE-01' THEN 'M04-PLATFORM-01'
        END
        FROM level_runs AS runs
        WHERE runs.run_id = state.run_id
          AND runs.level_id = 'LV-ROOM-05'
          AND state.mechanism_config_id IN (
              'M05-BRIDGE-01', 'M05-ENERGY-01', 'M05-REVERSE-01'
          )
        """
    )
    op.execute(
        """
        UPDATE rule_cast_events AS events
        SET target_id = CASE events.target_id
            WHEN 'M05-BRIDGE-01' THEN 'M02-BRIDGE-01'
            WHEN 'M05-ENERGY-01' THEN 'M03-ENERGY-01'
            WHEN 'M05-REVERSE-01' THEN 'M04-PLATFORM-01'
            ELSE events.target_id
        END,
        result = CASE
            WHEN events.result #>> '{combo,mechanism_id}' IS NULL THEN events.result
            ELSE jsonb_set(
                events.result,
                '{combo,mechanism_id}',
                to_jsonb(CASE events.result #>> '{combo,mechanism_id}'
                    WHEN 'M05-BRIDGE-01' THEN 'M02-BRIDGE-01'
                    WHEN 'M05-ENERGY-01' THEN 'M03-ENERGY-01'
                    WHEN 'M05-REVERSE-01' THEN 'M04-PLATFORM-01'
                    ELSE events.result #>> '{combo,mechanism_id}'
                END),
                true
            )
        END
        FROM level_runs AS runs
        WHERE runs.run_id = events.run_id
          AND runs.level_id = 'LV-ROOM-05'
        """
    )
    op.execute(
        """
        UPDATE player_rule_states AS state
        SET active_target_id = CASE state.active_target_id
            WHEN 'M05-BRIDGE-01' THEN 'M02-BRIDGE-01'
            WHEN 'M05-ENERGY-01' THEN 'M03-ENERGY-01'
            WHEN 'M05-REVERSE-01' THEN 'M04-PLATFORM-01'
        END
        FROM level_runs AS runs
        WHERE runs.run_id = state.run_id
          AND runs.level_id = 'LV-ROOM-05'
          AND state.active_target_id IN (
              'M05-BRIDGE-01', 'M05-ENERGY-01', 'M05-REVERSE-01'
          )
        """
    )
