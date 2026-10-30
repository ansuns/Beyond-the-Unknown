import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_vs5_progression"
down_revision = "0006_mech_catalog_align"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Objectives use concrete terminal states. The original constraint only
    # allowed generic states and made the GDD's objective checks impossible.
    op.drop_constraint(
        "ck_level_mechanism_target_state",
        "level_mechanism_catalog",
        type_="check",
    )
    op.create_check_constraint(
        "ck_level_mechanism_target_state",
        "level_mechanism_catalog",
        "target_state IN ('ACTIVE','LOCKED','TRIGGERED','OPEN','REVERSED',"
        "'ENDPOINT_LOCKED','ENDING_REVEALED')",
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
          ('DIS_COMBO_001','DIS_COMBO','LV-ROOM-02',
           '{"world_id":"WORLD-01","room_index":2}'::jsonb,
           NULL,'回声·注视组合发现',true),
          ('DIS_COMBO_002','DIS_COMBO','LV-ROOM-03',
           '{"world_id":"WORLD-01","room_index":3}'::jsonb,
           NULL,'回声·逆流组合发现',true),
          ('DIS_COMBO_003','DIS_COMBO','LV-ROOM-04',
           '{"world_id":"WORLD-01","room_index":4}'::jsonb,
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
