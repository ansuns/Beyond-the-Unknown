"""Complete the GDD mechanism ID migration across dependent JSON and event data."""

import sqlalchemy as sa
from alembic import op

revision = "0010_complete_mechanism_id_alignment"
down_revision = "0009_gdd_mechanism_ids"
branch_labels = None
depends_on = None


def _replace_id(table: str, column: str, old_id: str, new_id: str) -> None:
    # Table and column names are internal constants at the call sites below.
    op.get_bind().execute(
        sa.text(f"UPDATE {table} SET {column} = :new_id WHERE {column} = :old_id"),
        {"old_id": old_id, "new_id": new_id},
    )


def upgrade() -> None:
    # 0009 introduced canonical placeholders for two rows that already existed
    # under legacy IDs. Remove those duplicate placeholders before renaming
    # the original rows, preserving the original catalog's authored fields.
    op.drop_constraint(
        "fk_level_objective_mechanism", "level_objectives", type_="foreignkey"
    )
    op.execute(
        """
        DELETE FROM level_mechanism_catalog
        WHERE (level_id, mechanism_config_id) IN (
            ('LV-ROOM-03', 'M03-DOOR-01'),
            ('LV-HIDDEN-01', 'H01-END')
        )
        """
    )

    id_map = {
        "MECH-ROOM01-LIGHT-01": "M01-LIGHT-01",
        "MECH_ROOM03_DOOR_BARRIER": "M03-DOOR-01",
        "MECH-HIDDEN-ENDING-01": "H01-END",
    }
    for old_id, new_id in id_map.items():
        _replace_id("level_objectives", "mechanism_config_id", old_id, new_id)
        _replace_id("level_mechanism_catalog", "mechanism_config_id", old_id, new_id)

        # Preserve run state if both the old and new IDs have historical rows.
        op.get_bind().execute(
            sa.text(
                """
                UPDATE mechanism_states AS old_state
                SET state = old_state.state || new_state.state,
                    updated_at = GREATEST(old_state.updated_at, new_state.updated_at)
                FROM mechanism_states AS new_state
                WHERE old_state.run_id = new_state.run_id
                  AND old_state.player_id = new_state.player_id
                  AND old_state.mechanism_config_id = :old_id
                  AND new_state.mechanism_config_id = :new_id
                """
            ),
            {"old_id": old_id, "new_id": new_id},
        )
        op.get_bind().execute(
            sa.text(
                """
                DELETE FROM mechanism_states AS old_state
                WHERE old_state.mechanism_config_id = :old_id
                  AND EXISTS (
                    SELECT 1 FROM mechanism_states AS new_state
                    WHERE new_state.run_id = old_state.run_id
                      AND new_state.player_id = old_state.player_id
                      AND new_state.mechanism_config_id = :new_id
                  )
                """
            ),
            {"old_id": old_id, "new_id": new_id},
        )
        _replace_id("mechanism_states", "mechanism_config_id", old_id, new_id)

        _replace_id("rule_cast_events", "target_id", old_id, new_id)
        _replace_id("player_rule_states", "active_target_id", old_id, new_id)

    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_type = 'ENDING_CORE',
            trigger_rule = '["PLAYER_INTERACT"]'::jsonb,
            config = jsonb_build_object('config_status', 'PENDING_POSITION_AND_ART')
        WHERE level_id = 'LV-HIDDEN-01'
          AND mechanism_config_id = 'H01-END'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET config = jsonb_set(
            config, '{linked_mechanism_id}', to_jsonb('M03-DOOR-01'::text), true
        )
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'M03-ENERGY-01'
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
        UPDATE discovery_catalog
        SET trigger_condition = jsonb_set(
            trigger_condition,
            '{mechanism_id}',
            to_jsonb('M01-HIDEABLE-01'::text),
            true
        )
        WHERE discovery_id = 'DISC-HIDDEN-OBJ-ROOM01'
        """
    )

    # Update historical JSON payloads that retain mechanism identifiers.
    op.execute(
        """
        UPDATE rule_cast_events
        SET result = jsonb_set(
            result,
            '{effects}',
            COALESCE((
                SELECT jsonb_agg(
                    CASE effect->>'mechanism_id'
                        WHEN 'MECH-ROOM01-HIDDEN-01'
                            THEN jsonb_set(effect, '{mechanism_id}', '"M01-HIDEABLE-01"'::jsonb)
                        WHEN 'MECH_BRIDGE'
                            THEN jsonb_set(effect, '{mechanism_id}', '"M02-BRIDGE-01"'::jsonb)
                        WHEN 'MECH_ENERGY_GATE'
                            THEN jsonb_set(effect, '{mechanism_id}', '"M03-ENERGY-01"'::jsonb)
                        WHEN 'MECH_MOVING_PLATFORM'
                            THEN jsonb_set(effect, '{mechanism_id}', '"M04-PLATFORM-01"'::jsonb)
                        WHEN 'MECH-ROOM01-LIGHT-01'
                            THEN jsonb_set(effect, '{mechanism_id}', '"M01-LIGHT-01"'::jsonb)
                        WHEN 'MECH_ROOM03_DOOR_BARRIER'
                            THEN jsonb_set(effect, '{mechanism_id}', '"M03-DOOR-01"'::jsonb)
                        WHEN 'MECH-HIDDEN-ENDING-01'
                            THEN jsonb_set(effect, '{mechanism_id}', '"H01-END"'::jsonb)
                        ELSE effect
                    END
                )
                FROM jsonb_array_elements(COALESCE(result->'effects', '[]'::jsonb)) AS effect
            ), '[]'::jsonb),
            true
        )
        WHERE result ? 'effects'
        """
    )

    op.create_foreign_key(
        "fk_level_objective_mechanism",
        "level_objectives",
        "level_mechanism_catalog",
        ["level_id", "mechanism_config_id"],
        ["level_id", "mechanism_config_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Restore the legacy identifiers and the original dependent references."""
    op.drop_constraint(
        "fk_level_objective_mechanism", "level_objectives", type_="foreignkey"
    )
    reverse_map = {
        "M01-LIGHT-01": "MECH-ROOM01-LIGHT-01",
        "M03-DOOR-01": "MECH_ROOM03_DOOR_BARRIER",
        "H01-END": "MECH-HIDDEN-ENDING-01",
    }
    for new_id, old_id in reverse_map.items():
        _replace_id("level_objectives", "mechanism_config_id", new_id, old_id)
        _replace_id("level_mechanism_catalog", "mechanism_config_id", new_id, old_id)
        _replace_id("mechanism_states", "mechanism_config_id", new_id, old_id)
        _replace_id("rule_cast_events", "target_id", new_id, old_id)
        _replace_id("player_rule_states", "active_target_id", new_id, old_id)

    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_type = 'ENDING_GATE',
            trigger_rule = '["INTERACT"]'::jsonb,
            config = jsonb_build_object('config_status', 'PENDING_HIDDEN_ENDING_CONTENT')
        WHERE level_id = 'LV-HIDDEN-01'
          AND mechanism_config_id = 'MECH-HIDDEN-ENDING-01'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET config = jsonb_set(
            config, '{linked_mechanism_id}',
            to_jsonb('MECH_ROOM03_DOOR_BARRIER'::text), true
        )
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'M03-ENERGY-01'
        """
    )
    op.execute(
        """
        UPDATE hidden_routes
        SET trigger_mechanism_sequence =
            '["MECH_BRIDGE","MECH_ENERGY_GATE","MECH_MOVING_PLATFORM"]'::jsonb
        WHERE hidden_route_id = 'HIDDEN-ROUTE-01'
        """
    )
    op.execute(
        """
        UPDATE discovery_catalog
        SET trigger_condition = jsonb_set(
            trigger_condition,
            '{mechanism_id}',
            to_jsonb('MECH-ROOM01-HIDDEN-01'::text),
            true
        )
        WHERE discovery_id = 'DISC-HIDDEN-OBJ-ROOM01'
        """
    )
    op.create_foreign_key(
        "fk_level_objective_mechanism",
        "level_objectives",
        "level_mechanism_catalog",
        ["level_id", "mechanism_config_id"],
        ["level_id", "mechanism_config_id"],
        ondelete="CASCADE",
    )
