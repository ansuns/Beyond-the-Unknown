"""Add explicitly provisional geometry and tuning for rooms 02-05 and hidden ending."""

from alembic import op

revision = "0013_rooms_prototype_playable"
down_revision = "0012_room05_mechanism_alignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # These values are for the geometric gameplay prototype only. The separate
    # content_status marker keeps final art, balance and device acceptance open.
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
        UPDATE rule_catalog
        SET cooldown_ms = 1200,
            radius = 2.0,
            lease_timeout_ms = 5000,
            config_status = 'READY'
        WHERE rule_id = 'RULE_GAZE'
        """
    )
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = 1200,
            radius = 2.0,
            duration_ms = 1000,
            config_status = 'READY'
        WHERE rule_id = 'RULE_REVERSE'
        """
    )
    op.execute(
        """
        UPDATE combo_catalog
        SET time_window_ms = 10000,
            config_status = 'READY'
        WHERE combo_id IN ('COMBO-001', 'COMBO-002', 'COMBO-003')
        """
    )

    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET position_x = CASE
                WHEN level_id = 'LV-ROOM-02' AND mechanism_config_id = 'M02-BRIDGE-01' THEN 6.0
                WHEN level_id = 'LV-ROOM-03' AND mechanism_config_id = 'M03-ENERGY-01' THEN 4.0
                WHEN level_id = 'LV-ROOM-03' AND mechanism_config_id = 'M03-DOOR-01' THEN 8.0
                WHEN level_id = 'LV-ROOM-04' AND mechanism_config_id = 'M04-PLATFORM-01' THEN 4.0
                WHEN level_id = 'LV-ROOM-04' AND mechanism_config_id = 'M04-PLATFORM-02' THEN 8.0
                WHEN level_id = 'LV-ROOM-05' AND mechanism_config_id = 'M05-BRIDGE-01' THEN 3.0
                WHEN level_id = 'LV-ROOM-05' AND mechanism_config_id = 'M05-ENERGY-01' THEN 6.0
                WHEN level_id = 'LV-ROOM-05' AND mechanism_config_id = 'M05-REVERSE-01' THEN 9.0
                WHEN level_id = 'LV-ROOM-05' AND mechanism_config_id = 'M05-HIDDEN-GATE' THEN 11.0
                WHEN level_id = 'LV-HIDDEN-01' AND mechanism_config_id = 'H01-GATE' THEN 3.0
                WHEN level_id = 'LV-HIDDEN-01' AND mechanism_config_id = 'H01-END' THEN 9.0
            END,
            position_y = 4.0,
            config = config || jsonb_build_object(
                'config_status', 'READY',
                'content_status', 'PROTOTYPE_TUNING_PENDING',
                'prototype_only', true,
                'interaction_radius', 1.5
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
            'linked_mechanism_id', 'M04-PLATFORM-02'
        )
        WHERE level_id = 'LV-ROOM-04'
          AND mechanism_config_id = 'M04-PLATFORM-01'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET initial_state = 'TRIGGERED',
            config = config || jsonb_build_object('visible_by_default', true)
        WHERE level_id = 'LV-HIDDEN-01'
          AND mechanism_config_id = 'H01-GATE'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET config = config || jsonb_build_object(
            'requires_visible_mechanism_id', 'H01-GATE',
            'visible_by_default', true
        )
        WHERE level_id = 'LV-HIDDEN-01'
          AND mechanism_config_id = 'H01-END'
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
        UPDATE level_objectives
        SET config_status = 'CONTENT_PENDING'
        WHERE level_id = 'LV-HIDDEN-01'
          AND objective_id = 'ENDING_COMPLETE'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET position_x = NULL,
            position_y = NULL,
            config = (
                config - 'content_status' - 'prototype_only'
                        - 'interaction_radius' - 'visible_by_default'
                        - 'requires_visible_mechanism_id'
            ) || jsonb_build_object(
                'config_status',
                CASE
                    WHEN mechanism_config_id IN ('M05-HIDDEN-GATE', 'H01-GATE')
                        THEN 'PENDING_HIDDEN_ROUTE'
                    ELSE 'PENDING_POSITION_AND_ART'
                END
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
        SET config = config - 'linked_mechanism_id'
        WHERE level_id = 'LV-ROOM-04'
          AND mechanism_config_id = 'M04-PLATFORM-01'
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET initial_state = 'LOCKED'
        WHERE level_id = 'LV-HIDDEN-01'
          AND mechanism_config_id = 'H01-GATE'
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
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = NULL,
            radius = NULL,
            lease_timeout_ms = NULL,
            config_status = 'TUNING_REQUIRED'
        WHERE rule_id = 'RULE_GAZE'
        """
    )
    op.execute(
        """
        UPDATE rule_catalog
        SET cooldown_ms = NULL,
            radius = NULL,
            duration_ms = NULL,
            config_status = 'TUNING_REQUIRED'
        WHERE rule_id = 'RULE_REVERSE'
        """
    )
    op.execute(
        """
        UPDATE combo_catalog
        SET time_window_ms = NULL,
            config_status = 'TUNING_REQUIRED'
        WHERE combo_id IN ('COMBO-001', 'COMBO-002', 'COMBO-003')
        """
    )
