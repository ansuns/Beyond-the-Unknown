from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007_discovery_settlement"
down_revision = "0006_mech_catalog_align"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "level_objective_states",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("player_id", sa.Uuid(), primary_key=True),
        sa.Column("objective_id", sa.String(100), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("source_event_id", sa.String(128)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["run_id", "player_id"], ["level_runs.run_id", "level_runs.player_id"], ondelete="CASCADE"),
        sa.CheckConstraint("status IN ('PENDING','COMPLETED')", name="ck_level_objective_status"),
    )
    op.create_table(
        "hidden_route_catalog",
        sa.Column("route_id", sa.String(64), primary_key=True),
        sa.Column("prerequisite_levels", JSONB(), nullable=False),
        sa.Column("trigger_combos", JSONB(), nullable=False),
        sa.Column("trigger_mechanisms", JSONB(), nullable=False),
        sa.Column("result_level_id", sa.String(64), sa.ForeignKey("levels.level_id"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config_status", sa.String(32), nullable=False, server_default="READY"),
    )
    op.create_table(
        "player_hidden_routes",
        sa.Column("player_id", sa.Uuid(), primary_key=True),
        sa.Column("route_id", sa.String(64), primary_key=True),
        sa.Column("source_run_id", sa.Uuid(), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["player_id"], ["players.player_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_id"], ["hidden_route_catalog.route_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_run_id", "player_id"], ["level_runs.run_id", "level_runs.player_id"], ondelete="CASCADE"),
    )
    op.create_table(
        "score_award_config",
        sa.Column("reason", sa.String(32), primary_key=True),
        sa.Column(\n            "board_type",\n            postgresql.ENUM("EXPLORE", "CLEAR", "COLLECT", name="board_type", create_type=False),\n            nullable=False,\n        ),
        sa.Column("delta", sa.BigInteger()),
        sa.Column("config_status", sa.String(24), nullable=False, server_default="TUNING_REQUIRED"),
        sa.CheckConstraint("reason IN ('EXP_DISCOVER','CLEAR_STAGE','COLLECT_NEW')", name="ck_score_award_reason"),
        sa.CheckConstraint("delta IS NULL OR delta >= 0", name="ck_score_award_delta"),
    )
    op.execute("""
        INSERT INTO discovery_catalog
            (discovery_id, discovery_type, level_id, location, related_rule, display_name)
        VALUES
            ('DISC-RULE-ECHO','DIS_RULE_EFFECT',NULL,'{"scope":"WORLD"}'::jsonb,'RULE_ECHO','回声法则'),
            ('DISC-RULE-GAZE','DIS_RULE_EFFECT',NULL,'{"scope":"WORLD"}'::jsonb,'RULE_GAZE','注视法则'),
            ('DISC-RULE-REVERSE','DIS_RULE_EFFECT',NULL,'{"scope":"WORLD"}'::jsonb,'RULE_REVERSE','逆流法则'),
            ('DISC-COMBO-001','DIS_COMBO','LV-ROOM-02','{"room_index":2}'::jsonb,NULL,'回声与注视'),
            ('DISC-COMBO-002','DIS_COMBO','LV-ROOM-03','{"room_index":3}'::jsonb,NULL,'回声与逆流'),
            ('DISC-COMBO-003','DIS_COMBO','LV-ROOM-04','{"room_index":4}'::jsonb,NULL,'注视与逆流'),
            ('DISC-HIDDEN-OBJ-ROOM01-01','DIS_HIDDEN_OBJ','LV-ROOM-01','{"room_index":1}'::jsonb,'RULE_ECHO','遗忘森林的隐藏物'),
            ('DISC-PUZZLE-ROOM01-EXIT','DIS_PUZZLE','LV-ROOM-01','{"room_index":1}'::jsonb,NULL,'森林出口机关'),
            ('DISC-PUZZLE-ROOM02-BRIDGE','DIS_PUZZLE','LV-ROOM-02','{"room_index":2}'::jsonb,NULL,'浮现的桥梁'),
            ('DISC-PUZZLE-ROOM03-ENERGY','DIS_PUZZLE','LV-ROOM-03','{"room_index":3}'::jsonb,NULL,'逆流之门'),
            ('DISC-PUZZLE-ROOM04-PLATFORM','DIS_PUZZLE','LV-ROOM-04','{"room_index":4}'::jsonb,NULL,'终点平台'),
            ('DISC-HIDDEN-ROUTE-01','DIS_HIDDEN_AREA','LV-ROOM-05','{"route_id":"HIDDEN-ROUTE-01"}'::jsonb,NULL,'无界之外的隐秘入口'),
            ('DISC-ENDING-G009','DIS_ENDING','LV-HIDDEN-01','{"ending_id":"G-009"}'::jsonb,NULL,'无界之外')
        ON CONFLICT (discovery_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO collection_catalog
            (collection_id, codex_category, source_discovery_id, display_name, description, sort_order)
        VALUES
            ('COLL-RULE-ECHO','CAT_RULE','DISC-RULE-ECHO','回声法则','已理解回声法则',10),
            ('COLL-RULE-GAZE','CAT_RULE','DISC-RULE-GAZE','注视法则','已理解注视法则',20),
            ('COLL-RULE-REVERSE','CAT_RULE','DISC-RULE-REVERSE','逆流法则','已理解逆流法则',30),
            ('COLL-COMBO-001','CAT_RULE','DISC-COMBO-001','回声·注视','发现第一组组合',40),
            ('COLL-COMBO-002','CAT_RULE','DISC-COMBO-002','回声·逆流','发现第二组组合',50),
            ('COLL-COMBO-003','CAT_RULE','DISC-COMBO-003','注视·逆流','发现第三组组合',60),
            ('COLL-HIDDEN-OBJ-01','CAT_RELIC','DISC-HIDDEN-OBJ-ROOM01-01','森林的秘密','首次显现的隐藏物',70),
            ('COLL-EXIT-01','CAT_RELIC','DISC-PUZZLE-ROOM01-EXIT','森林出口机关','激活出口机关',80),
            ('COLL-BRIDGE-02','CAT_RELIC','DISC-PUZZLE-ROOM02-BRIDGE','浮空桥梁','稳定开启的桥梁',90),
            ('COLL-ENERGY-03','CAT_RELIC','DISC-PUZZLE-ROOM03-ENERGY','逆流之门','开启能量之门',100),
            ('COLL-PLATFORM-04','CAT_RELIC','DISC-PUZZLE-ROOM04-PLATFORM','终点平台','锁定移动平台',110),
            ('COLL-HIDDEN-ROUTE-01','CAT_AREA','DISC-HIDDEN-ROUTE-01','隐藏路线','开启首期隐藏路线',120),
            ('COLL-ENDING-G009','CAT_ENDING','DISC-ENDING-G009','无界之外','达成隐藏结局',130)
        ON CONFLICT (collection_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO hidden_route_catalog
            (route_id, prerequisite_levels, trigger_combos, trigger_mechanisms, result_level_id, is_enabled)
        VALUES
            ('HIDDEN-ROUTE-01',
             '["LV-ROOM-01","LV-ROOM-02","LV-ROOM-03","LV-ROOM-04","LV-ROOM-05"]'::jsonb,
             '["COMBO-001","COMBO-002","COMBO-003"]'::jsonb,
             '["M05-BRIDGE-01","M05-ENERGY-01","M05-REVERSE-01"]'::jsonb,
             'LV-HIDDEN-01', true)
        ON CONFLICT (route_id) DO NOTHING
    """)
    op.execute("""
        INSERT INTO score_award_config (reason, board_type, delta)
        VALUES ('EXP_DISCOVER','EXPLORE',NULL), ('CLEAR_STAGE','CLEAR',NULL), ('COLLECT_NEW','COLLECT',NULL)
        ON CONFLICT (reason) DO NOTHING
    """)
    op.execute("""
        UPDATE levels
        SET necessary_objectives = '["ROOM05_TARGET_A","ROOM05_TARGET_B","ROOM05_TARGET_C"]'::jsonb
        WHERE level_id = 'LV-ROOM-05'
    """)
    op.execute("""
        INSERT INTO level_mechanism_catalog
            (level_id, mechanism_config_id, mechanism_type, target_type, initial_state, target_state, trigger_rule, config)
        VALUES
            ('LV-HIDDEN-01','H01-ENDING-CORE','ENDING_CORE','MECHANISM','INACTIVE','TRIGGERED',
             '["PLAYER_INTERACT"]'::jsonb,
             jsonb_build_object('config_status','PENDING_POSITION_AND_ART','interaction_radius',NULL))
        ON CONFLICT (level_id, mechanism_config_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("score_award_config")
    op.drop_table("player_hidden_routes")
    op.drop_table("hidden_route_catalog")
    op.drop_table("level_objective_states")
    op.execute("DELETE FROM player_collections WHERE collection_id LIKE 'COLL-%'")
    op.execute("DELETE FROM collection_catalog WHERE collection_id LIKE 'COLL-%'")
    op.execute("DELETE FROM discovery_catalog WHERE discovery_id LIKE 'DISC-%'")
    op.execute("DELETE FROM level_mechanism_catalog WHERE level_id='LV-HIDDEN-01' AND mechanism_config_id='H01-ENDING-CORE'")
