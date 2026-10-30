import json

import sqlalchemy as sa
from alembic import op

revision = "0007_vs5_progression"
down_revision = "0006_mech_catalog_align"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_level_mechanism_target_state",
        "level_mechanism_catalog",
        type_="check",
    )
    op.create_check_constraint(
        "ck_level_mechanism_target_state",
        "level_mechanism_catalog",
        "target_state IN ('ACTIVE','LOCKED','TRIGGERED','REVEALED','OPEN',"
        "'REVERSED','ENDPOINT_LOCKED','ENDING_REVEALED')",
    )

    # Align the database catalog IDs with the versioned client/level contract.
    id_pairs = (
        ("LV-ROOM-01", "MECH-ROOM01-HIDDEN-01", "M01-HIDEABLE-01"),
        ("LV-ROOM-01", "MECH-ROOM01-LIGHT-01", "M01-LIGHT-01"),
        ("LV-ROOM-02", "MECH_BRIDGE", "M02-BRIDGE-01"),
        ("LV-ROOM-03", "MECH_ENERGY_GATE", "M03-ENERGY-01"),
        ("LV-ROOM-04", "MECH_MOVING_PLATFORM", "M04-PLATFORM-01"),
    )
    for level_id, old_id, new_id in id_pairs:
        op.get_bind().execute(
            sa.text("""
                UPDATE level_mechanism_catalog
                SET mechanism_config_id = :new_id
                WHERE level_id = :level_id AND mechanism_config_id = :old_id
            """),
            {"level_id": level_id, "old_id": old_id, "new_id": new_id},
        )
        op.get_bind().execute(
            sa.text("""
                UPDATE mechanism_states AS s
                SET mechanism_config_id = :new_id
                FROM level_runs AS r
                WHERE s.run_id = r.run_id
                  AND r.level_id = :level_id
                  AND s.mechanism_config_id = :old_id
            """),
            {"level_id": level_id, "old_id": old_id, "new_id": new_id},
        )

    # Replace legacy string objective IDs with the structured objective
    # contract from docs/engineering/levels/levels.v1.json.
    objectives = {
        "LV-ROOM-01": [
            {"objective_id": "OBJ-01-REVEAL", "mechanism_id": "M01-HIDEABLE-01", "target_state": "REVEALED"},
            {"objective_id": "OBJ-01-EXIT", "mechanism_id": "M01-EXIT-01", "target_state": "OPEN"},
        ],
        "LV-ROOM-02": [
            {"objective_id": "OBJ-02-BRIDGE", "mechanism_id": "M02-BRIDGE-01", "target_state": "OPEN", "required_combo": "COMBO-001"},
        ],
        "LV-ROOM-03": [
            {"objective_id": "OBJ-03-DOOR", "mechanism_id": "M03-DOOR-01", "target_state": "OPEN", "required_combo": "COMBO-002"},
        ],
        "LV-ROOM-04": [
            {"objective_id": "OBJ-04-PLATFORM", "mechanism_id": "M04-PLATFORM-01", "target_state": "ENDPOINT_LOCKED", "required_combo": "COMBO-003"},
        ],
        "LV-ROOM-05": [
            {"objective_id": "OBJ-05-BRIDGE", "mechanism_id": "M05-BRIDGE-01", "target_state": "OPEN", "required_combo": "COMBO-001"},
            {"objective_id": "OBJ-05-ENERGY", "mechanism_id": "M05-ENERGY-01", "target_state": "REVERSED", "required_combo": "COMBO-002"},
            {"objective_id": "OBJ-05-REVERSE", "mechanism_id": "M05-REVERSE-01", "target_state": "ENDPOINT_LOCKED", "required_combo": "COMBO-003"},
        ],
        "LV-HIDDEN-01": [
            {"objective_id": "OBJ-HIDDEN-END", "mechanism_id": "H01-END", "target_state": "ENDING_REVEALED"},
        ],
    }
    for level_id, required in objectives.items():
        op.get_bind().execute(
            sa.text("""
                UPDATE levels
                SET necessary_objectives = CAST(:objectives AS jsonb)
                WHERE level_id = :level_id
            """),
            {"level_id": level_id, "objectives": json.dumps(required)},
        )

    op.execute(
        """
        INSERT INTO level_mechanism_catalog
            (level_id, mechanism_config_id, mechanism_type, target_type,
             initial_state, target_state, trigger_rule, config)
        VALUES
          ('LV-ROOM-03','M03-DOOR-01','DOOR_BARRIER','MECHANISM',
           'INACTIVE','OPEN','["COMBO_EFFECT"]'::jsonb,
           '{"open_on_combo":"COMBO-002"}'::jsonb),
          ('LV-HIDDEN-01','H01-GATE','HIDDEN_GATE','MECHANISM',
           'LOCKED','TRIGGERED','["LEVEL_EVENT"]'::jsonb,
           '{"opened_by_route":"HIDDEN-ROUTE-01"}'::jsonb),
          ('LV-HIDDEN-01','H01-END','ENDING_CORE','MECHANISM',
           'INACTIVE','ENDING_REVEALED','["LEVEL_EVENT"]'::jsonb,
           '{"target_state":"ENDING_REVEALED"}'::jsonb)
        ON CONFLICT (level_id, mechanism_config_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog AS m
        SET target_state = objective.value->>'target_state'
        FROM levels AS l,
             LATERAL jsonb_array_elements(l.necessary_objectives) AS objective(value)
        WHERE m.level_id = l.level_id
          AND m.mechanism_config_id = objective.value->>'mechanism_id'
        """
    )

    op.create_table(
        "score_rule_config",
        sa.Column("board_type", sa.String(16), primary_key=True),
        sa.Column("reason", sa.String(32), primary_key=True),
        sa.Column("delta", sa.BigInteger(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("board_type IN ('EXPLORE','CLEAR','COLLECT')",
                           name="ck_score_rule_board"),
        sa.CheckConstraint("reason IN ('EXP_DISCOVER','CLEAR_STAGE','COLLECT_NEW')",
                           name="ck_score_rule_reason"),
        sa.CheckConstraint("delta IS NULL OR delta >= 0",
                           name="ck_score_rule_delta"),
        sa.CheckConstraint(
            "(is_enabled = false) OR (delta IS NOT NULL AND delta > 0)",
            name="ck_score_rule_enabled_delta",
        ),
    )
    op.execute(
        """
        INSERT INTO score_rule_config (board_type, reason, delta, is_enabled)
        VALUES
          ('EXPLORE','EXP_DISCOVER',NULL,false),
          ('CLEAR','CLEAR_STAGE',NULL,false),
          ('COLLECT','COLLECT_NEW',NULL,false)
        ON CONFLICT DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO discovery_catalog
            (discovery_id, discovery_type, level_id, location,
             related_rule, display_name, is_enabled)
        VALUES
          ('DIS_RULE_ECHO','DIS_RULE_EFFECT','LV-ROOM-01',
           '{"world_id":"WORLD-01","room_index":1}'::jsonb,
           'RULE_ECHO','回声法则发现',true),
          ('DIS_COMBO_001','DIS_COMBO',NULL,'{}'::jsonb,
           NULL,'回声·注视组合发现',true),
          ('DIS_COMBO_002','DIS_COMBO',NULL,'{}'::jsonb,
           NULL,'回声·逆流组合发现',true),
          ('DIS_COMBO_003','DIS_COMBO',NULL,'{}'::jsonb,
           NULL,'注视·逆流组合发现',true),
          ('DIS_HIDDEN_ROUTE_CLUE','DIS_HIDDEN_AREA','LV-ROOM-05',
           '{"world_id":"WORLD-01","room_index":5}'::jsonb,
           NULL,'隐藏路线线索',true),
          ('DIS_ENDING','DIS_ENDING','LV-HIDDEN-01',
           '{"world_id":"WORLD-01","hidden":true}'::jsonb,
           NULL,'世界之外结局',true)
        ON CONFLICT (discovery_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO collection_catalog
            (collection_id, codex_category, source_discovery_id,
             display_name, description, sort_order, is_enabled)
        VALUES
          ('COL_RULE_ECHO','CAT_RULE','DIS_RULE_ECHO','回声法则',
           '首次触发回声法则的记录。',10,true),
          ('COL_COMBO_001','CAT_RULE','DIS_COMBO_001','回声·注视',
           '首次发现回声与注视的组合。',20,true),
          ('COL_COMBO_002','CAT_RULE','DIS_COMBO_002','回声·逆流',
           '首次发现回声与逆流的组合。',30,true),
          ('COL_COMBO_003','CAT_RULE','DIS_COMBO_003','注视·逆流',
           '首次发现注视与逆流的组合。',40,true),
          ('COL_HIDDEN_ROUTE','CAT_AREA','DIS_HIDDEN_ROUTE_CLUE','隐藏路线线索',
           '首次发现隐藏路线线索。',50,true),
          ('COL_ENDING','CAT_ENDING','DIS_ENDING','世界之外',
           '达成首期隐藏结局。',60,true)
        ON CONFLICT (collection_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM level_mechanism_catalog
        WHERE (level_id, mechanism_config_id) IN (
          ('LV-ROOM-03','M03-DOOR-01'),
          ('LV-HIDDEN-01','H01-GATE'),
          ('LV-HIDDEN-01','H01-END')
        )
        """
    )
    op.drop_table("score_rule_config")
    op.execute(
        """
        DELETE FROM player_collections
        WHERE collection_id IN (
          'COL_RULE_ECHO','COL_COMBO_001','COL_COMBO_002',
          'COL_COMBO_003','COL_HIDDEN_ROUTE','COL_ENDING'
        )
        """
    )
    op.execute(
        """
        DELETE FROM collection_catalog
        WHERE collection_id IN (
          'COL_RULE_ECHO','COL_COMBO_001','COL_COMBO_002',
          'COL_COMBO_003','COL_HIDDEN_ROUTE','COL_ENDING'
        )
        """
    )
    op.execute(
        """
        DELETE FROM discovery_catalog
        WHERE discovery_id IN (
          'DIS_RULE_ECHO','DIS_COMBO_001','DIS_COMBO_002',
          'DIS_COMBO_003','DIS_HIDDEN_ROUTE_CLUE','DIS_ENDING'
        )
        """
    )
    op.execute("UPDATE level_mechanism_catalog SET target_state = 'TRIGGERED'")
    for level_id, old_id, new_id in (
        ("LV-ROOM-01", "MECH-ROOM01-HIDDEN-01", "M01-HIDEABLE-01"),
        ("LV-ROOM-01", "MECH-ROOM01-LIGHT-01", "M01-LIGHT-01"),
        ("LV-ROOM-02", "MECH_BRIDGE", "M02-BRIDGE-01"),
        ("LV-ROOM-03", "MECH_ENERGY_GATE", "M03-ENERGY-01"),
        ("LV-ROOM-04", "MECH_MOVING_PLATFORM", "M04-PLATFORM-01"),
    ):
        op.get_bind().execute(
            sa.text("""
                UPDATE level_mechanism_catalog
                SET mechanism_config_id = :old_id
                WHERE level_id = :level_id AND mechanism_config_id = :new_id
            """),
            {"level_id": level_id, "old_id": old_id, "new_id": new_id},
        )
        op.get_bind().execute(
            sa.text("""
                UPDATE mechanism_states AS s
                SET mechanism_config_id = :old_id
                FROM level_runs AS r
                WHERE s.run_id = r.run_id
                  AND r.level_id = :level_id
                  AND s.mechanism_config_id = :new_id
            """),
            {"level_id": level_id, "old_id": old_id, "new_id": new_id},
        )
    op.execute(
        """
        UPDATE levels SET necessary_objectives = CASE level_id
          WHEN 'LV-ROOM-01' THEN '["HIDDEN_TARGET_REVEALED","EXIT_ACTIVATED"]'::jsonb
          WHEN 'LV-ROOM-02' THEN '["BRIDGE_OPEN"]'::jsonb
          WHEN 'LV-ROOM-03' THEN '["ENERGY_DOOR_OPEN"]'::jsonb
          WHEN 'LV-ROOM-04' THEN '["MOVING_PLATFORM_LOCKED"]'::jsonb
          WHEN 'LV-ROOM-05' THEN '["ROOM05_TARGET_A","ROOM05_TARGET_B"]'::jsonb
          WHEN 'LV-HIDDEN-01' THEN '["ENDING_COMPLETE"]'::jsonb
          ELSE necessary_objectives
        END
        """
    )
    op.drop_constraint(
        "ck_level_mechanism_target_state",
        "level_mechanism_catalog",
        type_="check",
    )
    op.create_check_constraint(
        "ck_level_mechanism_target_state",
        "level_mechanism_catalog",
        "target_state IN ('ACTIVE','LOCKED','TRIGGERED')",
    )
