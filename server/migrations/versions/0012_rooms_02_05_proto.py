"""Configure provisional spatial prototypes for rooms 02–05 and the hidden ending."""

from alembic import op

revision = "0012_rooms_02_05_proto"
down_revision = "0011_room01_proto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # All values below are provisional gameplay scaffolding. Art and tuning
    # acceptance remain pending; this enables server-verified puzzle loops.
    op.execute(
        """
        UPDATE levels
        SET config = config || jsonb_build_object(
            'content_status', 'PROTOTYPE_TUNING_PENDING',
            'prototype_bounds', jsonb_build_object(
                'min_x', 0, 'max_x', 12, 'min_y', 0, 'max_y', 8
            ),
            'prototype_spawn', jsonb_build_object('x', 1, 'y', 4),
            'prototype_controls', jsonb_build_object(
                'movement_speed', 3.0, 'interaction_radius', 1.5
            )
        )
        WHERE level_id IN (
            'LV-ROOM-02', 'LV-ROOM-03', 'LV-ROOM-04',
            'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET position_x = CASE mechanism_config_id
                WHEN 'M02-BRIDGE-01' THEN 6.0
                WHEN 'M03-ENERGY-01' THEN 5.0
                WHEN 'M03-DOOR-01' THEN 10.5
                WHEN 'M04-PLATFORM-01' THEN 5.0
                WHEN 'M04-PLATFORM-02' THEN 8.5
                WHEN 'M05-BRIDGE-01' THEN 3.0
                WHEN 'M05-ENERGY-01' THEN 6.0
                WHEN 'M05-REVERSE-01' THEN 9.0
                WHEN 'M05-HIDDEN-GATE' THEN 11.0
                WHEN 'H01-GATE' THEN 3.0
                WHEN 'H01-END' THEN 10.0
            END,
            position_y = 4.0,
            config = config || jsonb_build_object(
                'content_status', 'PROTOTYPE_TUNING_PENDING'
            )
        WHERE (level_id, mechanism_config_id) IN (
            ('LV-ROOM-02', 'M02-BRIDGE-01'),
            ('LV-ROOM-03', 'M03-ENERGY-01'),
            ('LV-ROOM-03', 'M03-DOOR-01'),
            ('LV-ROOM-04', 'M04-PLATFORM-01'),
            ('LV-ROOM-04', 'M04-PLATFORM-02'),
            ('LV-ROOM-05', 'M05-BRIDGE-01'),
            ('LV-ROOM-05', 'M05-ENERGY-01'),
            ('LV-ROOM-05', 'M05-REVERSE-01'),
            ('LV-ROOM-05', 'M05-HIDDEN-GATE'),
            ('LV-HIDDEN-01', 'H01-GATE'),
            ('LV-HIDDEN-01', 'H01-END')
        )
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET config = config || jsonb_build_object(
            'interaction_radius', 1.5
        )
        WHERE level_id = 'LV-HIDDEN-01'
          AND mechanism_config_id = 'H01-END'
        """
    )
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = 1200,
            radius = 2.0,
            lease_timeout_ms = 1200,
            config_status = 'READY'
        WHERE rule_id = 'RULE_GAZE'
        """
    )
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = 1200,
            radius = 2.0,
            duration_ms = 5000,
            config_status = 'READY'
        WHERE rule_id = 'RULE_REVERSE'
        """
    )
    op.execute(
        """
        UPDATE combo_catalog
        SET time_window_ms = 8000,
            config_status = 'READY'
        WHERE combo_id IN ('COMBO-001', 'COMBO-002', 'COMBO-003')
        """
    )
    op.execute(
        """
        UPDATE level_objectives
        SET config_status = 'READY'
        WHERE level_id IN (
            'LV-ROOM-02', 'LV-ROOM-03', 'LV-ROOM-04',
            'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = NULL, radius = NULL, lease_timeout_ms = NULL,
            config_status = 'TUNING_REQUIRED'
        WHERE rule_id = 'RULE_GAZE'
        """
    )
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = NULL, radius = NULL, duration_ms = NULL,
            config_status = 'TUNING_REQUIRED'
        WHERE rule_id = 'RULE_REVERSE'
        """
    )
    op.execute(
        """
        UPDATE combo_catalog
        SET time_window_ms = NULL, config_status = 'TUNING_REQUIRED'
        WHERE combo_id IN ('COMBO-001', 'COMBO-002', 'COMBO-003')
        """
    )
    op.execute(
        """
        UPDATE level_objectives
        SET config_status = 'CONTENT_PENDING'
        WHERE level_id IN (
            'LV-ROOM-02', 'LV-ROOM-03', 'LV-ROOM-04',
            'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET position_x = NULL, position_y = NULL,
            config = config - 'content_status' - 'interaction_radius'
        WHERE level_id IN (
            'LV-ROOM-02', 'LV-ROOM-03', 'LV-ROOM-04',
            'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )
    op.execute(
        """
        UPDATE levels
        SET config = config - 'content_status' - 'prototype_bounds'
                      - 'prototype_spawn' - 'prototype_controls'
        WHERE level_id IN (
            'LV-ROOM-02', 'LV-ROOM-03', 'LV-ROOM-04',
            'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )
