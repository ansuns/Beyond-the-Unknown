import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ENUM, JSONB


revision = "0006_progress_discovery"
down_revision = "0005_rules_mechanisms"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discovery_catalog",
        sa.Column("trigger_condition", JSONB(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "discovery_catalog",
        sa.Column(
            "config_status",
            sa.String(32),
            nullable=False,
            server_default="CONTENT_PENDING",
        ),
    )
    op.add_column(
        "discovery_catalog",
        sa.Column("score_reason", sa.String(32), nullable=True),
    )

    op.create_table(
        "level_objectives",
        sa.Column(
            "level_id",
            sa.String(64),
            sa.ForeignKey("levels.level_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("objective_id", sa.String(100), primary_key=True),
        sa.Column("mechanism_config_id", sa.String(100), nullable=False),
        sa.Column("condition_type", sa.String(32), nullable=False),
        sa.Column("expected_state", sa.String(24), nullable=True),
        sa.Column("expected_value", sa.String(128), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "config_status",
            sa.String(32),
            nullable=False,
            server_default="CONTENT_PENDING",
        ),
        sa.ForeignKeyConstraint(
            ["level_id", "mechanism_config_id"],
            [
                "level_mechanism_catalog.level_id",
                "level_mechanism_catalog.mechanism_config_id",
            ],
            ondelete="CASCADE",
            name="fk_level_objective_mechanism",
        ),
        sa.CheckConstraint(
            "condition_type IN ('STATE_EQUALS','STATE_BOOLEAN','COMBO_APPLIED')",
            name="ck_level_objective_condition_type",
        ),
        sa.CheckConstraint(
            "config_status IN ('READY','CONTENT_PENDING','TUNING_REQUIRED')",
            name="ck_level_objective_config_status",
        ),
    )
    op.create_table(
        "hidden_routes",
        sa.Column("hidden_route_id", sa.String(64), primary_key=True),
        sa.Column("prerequisite_levels", JSONB(), nullable=False),
        sa.Column("trigger_level_id", sa.String(64), sa.ForeignKey("levels.level_id"), nullable=False),
        sa.Column("trigger_combo_sequence", JSONB(), nullable=False),
        sa.Column("trigger_mechanism_sequence", JSONB(), nullable=False),
        sa.Column("result_level_id", sa.String(64), sa.ForeignKey("levels.level_id"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "config_status",
            sa.String(32),
            nullable=False,
            server_default="CONTENT_PENDING",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(prerequisite_levels) = 5",
            name="ck_hidden_route_five_prerequisites",
        ),
        sa.CheckConstraint(
            "jsonb_array_length(trigger_combo_sequence) = 3",
            name="ck_hidden_route_three_combos",
        ),
    )
    op.create_table(
        "player_unlocked_hidden_routes",
        sa.Column(
            "player_id",
            sa.Uuid(),
            sa.ForeignKey("players.player_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "hidden_route_id",
            sa.String(64),
            sa.ForeignKey("hidden_routes.hidden_route_id"),
            primary_key=True,
        ),
        sa.Column("source_run_id", sa.Uuid(), nullable=True),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["source_run_id", "player_id"],
            ["level_runs.run_id", "level_runs.player_id"],
            name="fk_player_hidden_route_source_run",
        ),
    )
    op.create_table(
        "score_rule_config",
        sa.Column("reason", sa.String(32), primary_key=True),
        sa.Column("board_type", ENUM("EXPLORE", "CLEAR", "COLLECT", name="board_type", create_type=False), nullable=False),
        sa.Column("delta", sa.BigInteger(), nullable=True),
        sa.Column(
            "config_status",
            sa.String(32),
            nullable=False,
            server_default="TUNING_REQUIRED",
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint(
            "reason IN ('EXP_DISCOVER','CLEAR_STAGE','COLLECT_NEW')",
            name="ck_score_rule_reason",
        ),
        sa.CheckConstraint("delta IS NULL OR delta >= 0", name="ck_score_rule_delta"),
    )
    op.create_table(
        "reward_conditions",
        sa.Column("condition_id", sa.String(160), primary_key=True),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("condition_config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("reward_id", sa.String(100), sa.ForeignKey("rewards.reward_id", deferrable=True, initially="DEFERRED"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "config_status",
            sa.String(32),
            nullable=False,
            server_default="CONTENT_PENDING",
        ),
        sa.CheckConstraint(
            "trigger_type IN ('SCORE','COLLECTION','DISCOVERY','COMPOSITE','SEASON_RANK','SETTLEMENT')",
            name="ck_reward_condition_trigger_type",
        ),
    )
    op.create_foreign_key(
        "fk_rewards_condition_ref",
        "rewards",
        "reward_conditions",
        ["condition_ref"],
        ["condition_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        "fk_score_event_run_owner",
        "score_events",
        "level_runs",
        ["run_id", "player_id"],
        ["run_id", "player_id"],
    )
    op.create_index(
        "idx_reward_conditions_trigger_type",
        "reward_conditions",
        ["trigger_type", "is_enabled", "config_status"],
    )
    op.create_index(
        "idx_player_collections_player_category",
        "player_collections",
        ["player_id", "codex_category"],
    )

    op.execute(
        """
        INSERT INTO score_rule_config (reason, board_type, delta, config_status)
        VALUES
            ('EXP_DISCOVER', 'EXPLORE', NULL, 'TUNING_REQUIRED'),
            ('CLEAR_STAGE', 'CLEAR', NULL, 'TUNING_REQUIRED'),
            ('COLLECT_NEW', 'COLLECT', NULL, 'TUNING_REQUIRED')
        ON CONFLICT (reason) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO level_mechanism_catalog
            (level_id, mechanism_config_id, mechanism_type, target_type,
             initial_state, target_state, trigger_rule, config, is_enabled)
        VALUES
            ('LV-ROOM-01', 'MECH-ROOM01-EXIT-01', 'EXIT', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["INTERACT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_INTERACTION_RANGE'), true),
            ('LV-ROOM-03', 'MECH_ROOM03_DOOR_BARRIER', 'DOOR_BARRIER', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["COMBO_EFFECT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_POSITION_AND_ART'), true),
            ('LV-ROOM-05', 'MECH_BRIDGE', 'PLATFORM_BRIDGE', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT","COMBO_EFFECT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_POSITION_AND_ART', 'visible_by_default', false), true),
            ('LV-ROOM-05', 'MECH_ENERGY_GATE', 'ENERGY_NODE', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT","COMBO_EFFECT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_POSITION_AND_ART', 'initial_direction', 1), true),
            ('LV-ROOM-05', 'MECH_MOVING_PLATFORM', 'MOVING_OBJECT', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT","COMBO_EFFECT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_POSITION_AND_ART', 'initial_direction', 1), true),
            ('LV-HIDDEN-01', 'MECH-HIDDEN-ENDING-01', 'ENDING_GATE', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["INTERACT"]'::jsonb,
             jsonb_build_object('config_status', 'PENDING_HIDDEN_ENDING_CONTENT'), true)
        ON CONFLICT (level_id, mechanism_config_id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE level_mechanism_catalog
        SET config = jsonb_set(
            config,
            '{linked_mechanism_id}',
            to_jsonb('MECH_ROOM03_DOOR_BARRIER'::text),
            true
        )
        WHERE level_id = 'LV-ROOM-03'
          AND mechanism_config_id = 'MECH_ENERGY_GATE'
        """
    )
    op.execute(
        """
        UPDATE levels
        SET necessary_objectives =
            '["ROOM05_COMBO_001","ROOM05_COMBO_002","ROOM05_COMBO_003"]'::jsonb
        WHERE level_id = 'LV-ROOM-05'
        """
    )
    op.execute(
        """
        INSERT INTO level_objectives
            (level_id, objective_id, mechanism_config_id, condition_type,
             expected_state, expected_value, is_required, config, config_status)
        VALUES
            ('LV-ROOM-01', 'HIDDEN_TARGET_REVEALED', 'MECH-ROOM01-HIDDEN-01',
             'STATE_BOOLEAN', NULL, 'true', true,
             jsonb_build_object('state_key', 'visible'), 'READY'),
            ('LV-ROOM-01', 'EXIT_ACTIVATED', 'MECH-ROOM01-EXIT-01',
             'STATE_EQUALS', 'TRIGGERED', NULL, true, '{}'::jsonb, 'CONTENT_PENDING'),
            ('LV-ROOM-02', 'BRIDGE_OPEN', 'MECH_BRIDGE',
             'STATE_EQUALS', 'TRIGGERED', NULL, true, '{}'::jsonb, 'READY'),
            ('LV-ROOM-03', 'ENERGY_DOOR_OPEN', 'MECH_ROOM03_DOOR_BARRIER',
             'STATE_EQUALS', 'TRIGGERED', NULL, true, '{}'::jsonb, 'READY'),
            ('LV-ROOM-04', 'MOVING_PLATFORM_LOCKED', 'MECH_MOVING_PLATFORM',
             'STATE_EQUALS', 'TRIGGERED', NULL, true, '{}'::jsonb, 'READY'),
            ('LV-ROOM-05', 'ROOM05_COMBO_001', 'MECH_BRIDGE',
             'COMBO_APPLIED', NULL, 'COMBO-001', true, '{}'::jsonb, 'READY'),
            ('LV-ROOM-05', 'ROOM05_COMBO_002', 'MECH_ENERGY_GATE',
             'COMBO_APPLIED', NULL, 'COMBO-002', true, '{}'::jsonb, 'READY'),
            ('LV-ROOM-05', 'ROOM05_COMBO_003', 'MECH_MOVING_PLATFORM',
             'COMBO_APPLIED', NULL, 'COMBO-003', true, '{}'::jsonb, 'READY'),
            ('LV-HIDDEN-01', 'ENDING_COMPLETE', 'MECH-HIDDEN-ENDING-01',
             'STATE_EQUALS', 'TRIGGERED', NULL, true, '{}'::jsonb, 'CONTENT_PENDING')
        ON CONFLICT (level_id, objective_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO hidden_routes
            (hidden_route_id, prerequisite_levels, trigger_level_id,
             trigger_combo_sequence, trigger_mechanism_sequence,
             result_level_id, is_enabled, config_status)
        VALUES
            ('HIDDEN-ROUTE-01',
             '["LV-ROOM-01","LV-ROOM-02","LV-ROOM-03","LV-ROOM-04","LV-ROOM-05"]'::jsonb,
             'LV-ROOM-05',
             '["COMBO-001","COMBO-002","COMBO-003"]'::jsonb,
             '["MECH_BRIDGE","MECH_ENERGY_GATE","MECH_MOVING_PLATFORM"]'::jsonb,
             'LV-HIDDEN-01', true, 'READY')
        ON CONFLICT (hidden_route_id) DO NOTHING
        """
    )

    op.execute(
        """
        INSERT INTO discovery_catalog
            (discovery_id, discovery_type, level_id, location, related_rule,
             display_name, is_enabled, trigger_condition, config_status, score_reason)
        VALUES
            ('DISC-RULE-ECHO', 'DIS_RULE_EFFECT', NULL,
             jsonb_build_object('world_id', 'WORLD_01'), 'RULE_ECHO',
             '回声法则', true,
             jsonb_build_object('event_type', 'RULE_EFFECT', 'rule_id', 'RULE_ECHO'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-RULE-GAZE', 'DIS_RULE_EFFECT', NULL,
             jsonb_build_object('world_id', 'WORLD_01'), 'RULE_GAZE',
             '注视法则', true,
             jsonb_build_object('event_type', 'RULE_EFFECT', 'rule_id', 'RULE_GAZE'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-RULE-REVERSE', 'DIS_RULE_EFFECT', NULL,
             jsonb_build_object('world_id', 'WORLD_01'), 'RULE_REVERSE',
             '逆流法则', true,
             jsonb_build_object('event_type', 'RULE_EFFECT', 'rule_id', 'RULE_REVERSE'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-COMBO-001', 'DIS_COMBO', 'LV-ROOM-02',
             jsonb_build_object('level_id', 'LV-ROOM-02'), NULL,
             '回声·注视组合', true,
             jsonb_build_object('event_type', 'COMBO', 'combo_id', 'COMBO-001'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-COMBO-002', 'DIS_COMBO', 'LV-ROOM-03',
             jsonb_build_object('level_id', 'LV-ROOM-03'), NULL,
             '回声·逆流组合', true,
             jsonb_build_object('event_type', 'COMBO', 'combo_id', 'COMBO-002'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-COMBO-003', 'DIS_COMBO', 'LV-ROOM-04',
             jsonb_build_object('level_id', 'LV-ROOM-04'), NULL,
             '注视·逆流组合', true,
             jsonb_build_object('event_type', 'COMBO', 'combo_id', 'COMBO-003'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-HIDDEN-OBJ-ROOM01', 'DIS_HIDDEN_OBJ', 'LV-ROOM-01',
             jsonb_build_object('level_id', 'LV-ROOM-01'), NULL,
             '遗忘森林中的隐藏物体', true,
             jsonb_build_object('event_type', 'MECHANISM_VISIBLE', 'mechanism_id', 'MECH-ROOM01-HIDDEN-01'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-HIDDEN-ROUTE-01', 'DIS_HIDDEN_AREA', 'LV-ROOM-05',
             jsonb_build_object('level_id', 'LV-ROOM-05'), NULL,
             '隐藏路线', true,
             jsonb_build_object('event_type', 'HIDDEN_ROUTE_UNLOCK', 'route_id', 'HIDDEN-ROUTE-01'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-PUZZLE-ROOM01', 'DIS_PUZZLE', 'LV-ROOM-01',
             jsonb_build_object('level_id', 'LV-ROOM-01'), NULL,
             '探索房间 1 完成', true,
             jsonb_build_object('event_type', 'LEVEL_COMPLETE', 'level_id', 'LV-ROOM-01'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-PUZZLE-ROOM02', 'DIS_PUZZLE', 'LV-ROOM-02',
             jsonb_build_object('level_id', 'LV-ROOM-02'), NULL,
             '探索房间 2 完成', true,
             jsonb_build_object('event_type', 'LEVEL_COMPLETE', 'level_id', 'LV-ROOM-02'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-PUZZLE-ROOM03', 'DIS_PUZZLE', 'LV-ROOM-03',
             jsonb_build_object('level_id', 'LV-ROOM-03'), NULL,
             '探索房间 3 完成', true,
             jsonb_build_object('event_type', 'LEVEL_COMPLETE', 'level_id', 'LV-ROOM-03'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-PUZZLE-ROOM04', 'DIS_PUZZLE', 'LV-ROOM-04',
             jsonb_build_object('level_id', 'LV-ROOM-04'), NULL,
             '探索房间 4 完成', true,
             jsonb_build_object('event_type', 'LEVEL_COMPLETE', 'level_id', 'LV-ROOM-04'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-PUZZLE-ROOM05', 'DIS_PUZZLE', 'LV-ROOM-05',
             jsonb_build_object('level_id', 'LV-ROOM-05'), NULL,
             '探索房间 5 完成', true,
             jsonb_build_object('event_type', 'LEVEL_COMPLETE', 'level_id', 'LV-ROOM-05'),
             'READY', 'EXP_DISCOVER'),
            ('DISC-ENDING-01', 'DIS_ENDING', 'LV-HIDDEN-01',
             jsonb_build_object('level_id', 'LV-HIDDEN-01'), NULL,
             '无界之外', true,
             jsonb_build_object('event_type', 'LEVEL_COMPLETE', 'level_id', 'LV-HIDDEN-01'),
             'READY', 'EXP_DISCOVER')
        ON CONFLICT (discovery_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO collection_catalog
            (collection_id, codex_category, source_discovery_id, display_name,
             description, sort_order, is_enabled)
        VALUES
            ('COLL-RULE-ECHO', 'CAT_RULE', 'DISC-RULE-ECHO', '回声法则', '已发现回声法则。', 10, true),
            ('COLL-RULE-GAZE', 'CAT_RULE', 'DISC-RULE-GAZE', '注视法则', '已发现注视法则。', 20, true),
            ('COLL-RULE-REVERSE', 'CAT_RULE', 'DISC-RULE-REVERSE', '逆流法则', '已发现逆流法则。', 30, true),
            ('COLL-COMBO-001', 'CAT_RULE', 'DISC-COMBO-001', '回声·注视', '已发现预设组合。', 40, true),
            ('COLL-COMBO-002', 'CAT_RULE', 'DISC-COMBO-002', '回声·逆流', '已发现预设组合。', 50, true),
            ('COLL-COMBO-003', 'CAT_RULE', 'DISC-COMBO-003', '注视·逆流', '已发现预设组合。', 60, true),
            ('COLL-HIDDEN-OBJ-ROOM01', 'CAT_RELIC', 'DISC-HIDDEN-OBJ-ROOM01', '遗忘森林隐藏物体', '已发现隐藏物体。', 10, true),
            ('COLL-HIDDEN-ROUTE-01', 'CAT_AREA', 'DISC-HIDDEN-ROUTE-01', '隐藏路线', '已开启隐藏路线。', 10, true),
            ('COLL-ENDING-01', 'CAT_ENDING', 'DISC-ENDING-01', '隐藏结局', '已达成首期隐藏结局。', 10, true)
        ON CONFLICT (collection_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_player_collections_player_category", table_name="player_collections")
    op.drop_index("idx_reward_conditions_trigger_type", table_name="reward_conditions")
    op.drop_constraint("fk_score_event_run_owner", "score_events", type_="foreignkey")
    op.drop_constraint("fk_rewards_condition_ref", "rewards", type_="foreignkey")
    op.drop_table("reward_conditions")
    op.drop_table("score_rule_config")
    op.drop_table("player_unlocked_hidden_routes")
    op.drop_table("hidden_routes")
    op.drop_table("level_objectives")
    op.drop_column("discovery_catalog", "score_reason")
    op.drop_column("discovery_catalog", "config_status")
    op.drop_column("discovery_catalog", "trigger_condition")
