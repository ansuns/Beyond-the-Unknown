"""Store room-specific law-combo presets in each level's public config."""

from alembic import op

revision = "0014_room_prototype_combo_presets"
down_revision = "0013_rooms_prototype_playable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE levels AS level
        SET config = level.config || jsonb_build_object(
            'prototype_combos', presets.prototype_combos
        )
        FROM (
            VALUES
                ('LV-ROOM-01', '[]'::jsonb),
                ('LV-ROOM-02',
                 '[{"combo_id":"COMBO-001","target_mechanism_id":"M02-BRIDGE-01","rule_sequence":["RULE_ECHO","RULE_GAZE"],"display_name":"施放组合一"}]'::jsonb),
                ('LV-ROOM-03',
                 '[{"combo_id":"COMBO-002","target_mechanism_id":"M03-ENERGY-01","rule_sequence":["RULE_ECHO","RULE_REVERSE"],"display_name":"施放组合二"}]'::jsonb),
                ('LV-ROOM-04',
                 '[{"combo_id":"COMBO-003","target_mechanism_id":"M04-PLATFORM-01","rule_sequence":["RULE_GAZE","RULE_REVERSE"],"display_name":"施放组合三"}]'::jsonb),
                ('LV-ROOM-05',
                 '[
                    {"combo_id":"COMBO-001","target_mechanism_id":"M05-BRIDGE-01","rule_sequence":["RULE_ECHO","RULE_GAZE"],"display_name":"组合一·桥梁"},
                    {"combo_id":"COMBO-002","target_mechanism_id":"M05-ENERGY-01","rule_sequence":["RULE_ECHO","RULE_REVERSE"],"display_name":"组合二·能量"},
                    {"combo_id":"COMBO-003","target_mechanism_id":"M05-REVERSE-01","rule_sequence":["RULE_GAZE","RULE_REVERSE"],"display_name":"组合三·逆流"}
                 ]'::jsonb),
                ('LV-HIDDEN-01', '[]'::jsonb)
        ) AS presets(level_id, prototype_combos)
        WHERE level.level_id = presets.level_id
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE levels
        SET config = config - 'prototype_combos'
        WHERE level_id IN (
            'LV-ROOM-01', 'LV-ROOM-02', 'LV-ROOM-03',
            'LV-ROOM-04', 'LV-ROOM-05', 'LV-HIDDEN-01'
        )
        """
    )
