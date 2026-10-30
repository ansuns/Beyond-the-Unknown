"""Complete ROOM-01 mechanism catalog IDs from the canonical GDD.

This migration adds the missing exit catalog row and renames the legacy light
mechanism identifier. Spatial coordinates and interaction tuning intentionally
remain pending; the row cannot be interacted with until content configuration
provides a validated position and radius.
"""

from alembic import op
import sqlalchemy as sa

revision = "0010_room01_catalog_completion"
down_revision = "0009_gdd_mechanism_ids"
branch_labels = None
depends_on = None


def _rename(column_table: str, old_id: str, new_id: str, column: str = "mechanism_config_id") -> None:
    op.get_bind().execute(
        sa.text(
            f"UPDATE {column_table} SET {column} = :new_id WHERE {column} = :old_id"
        ),
        {"old_id": old_id, "new_id": new_id},
    )


def upgrade() -> None:
    # Keep all persisted references on the canonical GDD identifier.
    _rename("level_objectives", "MECH-ROOM01-LIGHT-01", "M01-LIGHT-01")
    _rename("mechanism_states", "MECH-ROOM01-LIGHT-01", "M01-LIGHT-01")
    _rename("level_mechanism_catalog", "MECH-ROOM01-LIGHT-01", "M01-LIGHT-01")
    _rename("combo_catalog", "MECH-ROOM01-LIGHT-01", "M01-LIGHT-01", "target_mechanism_id")

    # GDD objective OBJ-01-EXIT references M01-EXIT-01, which was missing
    # from the original server catalog. Do not guess position/radius values.
    op.execute(
        """
        INSERT INTO level_mechanism_catalog
            (level_id, mechanism_config_id, mechanism_type, target_type,
             initial_state, target_state, trigger_rule, config, is_enabled)
        VALUES
            ('LV-ROOM-01', 'M01-EXIT-01', 'EXIT_GATE', 'MECHANISM',
             'LOCKED', 'OPEN', '["PLAYER_INTERACT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART","interaction_radius":null}'::jsonb,
             true)
        ON CONFLICT (level_id, mechanism_config_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM level_mechanism_catalog
        WHERE level_id = 'LV-ROOM-01'
          AND mechanism_config_id = 'M01-EXIT-01'
        """
    )
    _rename("level_objectives", "M01-LIGHT-01", "MECH-ROOM01-LIGHT-01")
    _rename("mechanism_states", "M01-LIGHT-01", "MECH-ROOM01-LIGHT-01")
    _rename("level_mechanism_catalog", "M01-LIGHT-01", "MECH-ROOM01-LIGHT-01")
    _rename("combo_catalog", "M01-LIGHT-01", "MECH-ROOM01-LIGHT-01", "target_mechanism_id")
