"""Align persisted mechanism catalog IDs with the canonical GDD level data."""

import sqlalchemy as sa
from alembic import op

revision = "0009_gdd_mechanism_ids"
down_revision = "0008_season_outbox"
branch_labels = None
depends_on = None


def _update_ids(table: str, old_id: str, new_id: str) -> None:
    # Table names are fixed internal constants at the call sites below.
    op.get_bind().execute(
        sa.text(
            f"UPDATE {table} SET mechanism_config_id = :new_id "
            "WHERE mechanism_config_id = :old_id"
        ),
        {"old_id": old_id, "new_id": new_id},
    )


def upgrade() -> None:
    """Rename legacy IDs and add catalog entries missing from the GDD mapping."""
    id_map = {
        "MECH-ROOM01-HIDDEN-01": "M01-HIDEABLE-01",
        "MECH_BRIDGE": "M02-BRIDGE-01",
        "MECH_ENERGY_GATE": "M03-ENERGY-01",
        "MECH_MOVING_PLATFORM": "M04-PLATFORM-01",
    }
    # Temporarily remove the composite FK while both sides are renamed.
    op.drop_constraint(
        "fk_level_objective_mechanism", "level_objectives", type_="foreignkey"
    )
    for old_id, new_id in id_map.items():
        _update_ids("level_objectives", old_id, new_id)
        _update_ids("mechanism_states", old_id, new_id)
        _update_ids("level_mechanism_catalog", old_id, new_id)
    op.create_foreign_key(
        "fk_level_objective_mechanism",
        "level_objectives",
        "level_mechanism_catalog",
        ["level_id", "mechanism_config_id"],
        ["level_id", "mechanism_config_id"],
        ondelete="CASCADE",
    )

    # Catalog entries are present for future content work. Their interaction
    # positions, art and rule tuning remain pending and must not be inferred.
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
    op.drop_constraint(
        "fk_level_objective_mechanism", "level_objectives", type_="foreignkey"
    )
    for new_id, old_id in reverse_map.items():
        _update_ids("level_objectives", new_id, old_id)
        _update_ids("mechanism_states", new_id, old_id)
        _update_ids("level_mechanism_catalog", new_id, old_id)
    op.create_foreign_key(
        "fk_level_objective_mechanism",
        "level_objectives",
        "level_mechanism_catalog",
        ["level_id", "mechanism_config_id"],
        ["level_id", "mechanism_config_id"],
        ondelete="CASCADE",
    )
