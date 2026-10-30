import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_level_mechanism_catalog_alignment"
down_revision = "0005_rules_mechanisms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_config_id = 'M05-BRIDGE-01'
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id = 'MECH-ROOM05-TARGET-A'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_config_id = 'M05-ENERGY-01'
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id = 'MECH-ROOM05-TARGET-B'
        """
    )
    op.execute(
        """
        UPDATE mechanism_states AS s
        SET mechanism_config_id = CASE s.mechanism_config_id
            WHEN 'MECH-ROOM05-TARGET-A' THEN 'M05-BRIDGE-01'
            WHEN 'MECH-ROOM05-TARGET-B' THEN 'M05-ENERGY-01'
        END
        FROM level_runs AS r
        WHERE s.run_id = r.run_id
          AND r.level_id = 'LV-ROOM-05'
          AND s.mechanism_config_id IN (
              'MECH-ROOM05-TARGET-A', 'MECH-ROOM05-TARGET-B'
          )
        """
    )
    op.execute(
        """
        INSERT INTO level_mechanism_catalog
            (level_id, mechanism_config_id, mechanism_type, target_type,
             initial_state, target_state, trigger_rule, config)
        VALUES
            ('LV-ROOM-01', 'M01-EXIT-01', 'EXIT_GATE', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["PLAYER_INTERACT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_POSITION_AND_ART')),
            ('LV-ROOM-05', 'M05-REVERSE-01', 'MOVING_OBJECT', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT","COMBO_EFFECT"]'::jsonb,
             jsonb_build_object(
                 'config_status', 'PENDING_POSITION_AND_ART',
                 'initial_direction', 1
             )),
            ('LV-ROOM-05', 'M05-HIDDEN-GATE', 'HIDDEN_GATE', 'MECHANISM',
             'LOCKED', 'TRIGGERED', '["LEVEL_EVENT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_HIDDEN_ROUTE'))
        ON CONFLICT (level_id, mechanism_config_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM level_mechanism_catalog
        WHERE (level_id, mechanism_config_id) IN (
            ('LV-ROOM-01', 'M01-EXIT-01'),
            ('LV-ROOM-05', 'M05-REVERSE-01'),
            ('LV-ROOM-05', 'M05-HIDDEN-GATE')
        )
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_config_id = 'MECH-ROOM05-TARGET-A'
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id = 'M05-BRIDGE-01'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET mechanism_config_id = 'MECH-ROOM05-TARGET-B'
        WHERE level_id = 'LV-ROOM-05'
          AND mechanism_config_id = 'M05-ENERGY-01'
        """
    )
