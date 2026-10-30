from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0004_levels_and_enter_requests"
down_revision = "0003_map_instance_members"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "levels",
        sa.Column("level_id", sa.String(64), primary_key=True),
        sa.Column("level_name", sa.String(120), nullable=False),
        sa.Column("map_id", sa.String(64), sa.ForeignKey("maps.map_id"), nullable=False),
        sa.Column("entrance_id", sa.String(64), nullable=False, unique=True),
        sa.Column("room_index", sa.Integer(), nullable=True),
        sa.Column("target_duration_min", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("target_duration_max", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("hard_time_limit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("time_limit_seconds", sa.Integer(), nullable=True),
        sa.Column("repeatable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("repeat_reward_mode", sa.String(16), nullable=False, server_default="NONE"),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("required_laws", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "necessary_objectives",
            JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.CheckConstraint(
            "room_index IS NULL OR room_index BETWEEN 1 AND 5",
            name="ck_levels_room_index",
        ),
        sa.CheckConstraint(
            "target_duration_min >= 0 AND target_duration_max >= target_duration_min",
            name="ck_levels_target_duration",
        ),
        sa.CheckConstraint(
            "(hard_time_limit = false AND time_limit_seconds IS NULL) OR "
            "(hard_time_limit = true AND time_limit_seconds > 0)",
            name="ck_levels_time_limit",
        ),
        sa.CheckConstraint(
            "repeat_reward_mode IN ('NONE','REDUCED','FULL')",
            name="ck_levels_repeat_reward_mode",
        ),
        sa.CheckConstraint(
            "(is_hidden = true AND room_index IS NULL) OR "
            "(is_hidden = false AND room_index IS NOT NULL)",
            name="ck_levels_hidden_room_index",
        ),
    )
    op.create_index(
        "uq_levels_room_index",
        "levels",
        ["room_index"],
        unique=True,
        postgresql_where=sa.text("room_index IS NOT NULL"),
    )
    op.create_foreign_key(
        "fk_level_runs_level",
        "level_runs",
        "levels",
        ["level_id"],
        ["level_id"],
    )
    op.create_index(
        "uq_level_runs_one_active_per_player",
        "level_runs",
        ["player_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('CREATED','RUNNING')"),
    )
    op.create_table(
        "level_enter_requests",
        sa.Column(
            "player_id",
            sa.Uuid(),
            sa.ForeignKey("players.player_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("idempotency_key", sa.String(200), primary_key=True),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["run_id", "player_id"],
            ["level_runs.run_id", "level_runs.player_id"],
            ondelete="CASCADE",
            name="fk_level_enter_request_run_owner",
        ),
    )

    op.execute(
        """
        INSERT INTO levels (
            level_id, level_name, map_id, entrance_id, room_index,
            required_laws, necessary_objectives, is_hidden, is_enabled, config
        )
        VALUES
        (
            'LV-ROOM-01', '探索房间 1', 'MAP_MAIN_001', 'ENT-ROOM-01', 1,
            '["RULE_ECHO"]'::jsonb,
            '["HIDDEN_TARGET_REVEALED","EXIT_ACTIVATED"]'::jsonb,
            false, true,
            '{"config_status":"PROTOTYPE_PENDING_LEVEL_ART","mechanisms":["HIDEABLE","LIGHT_REVEAL"]}'::jsonb
        ),
        (
            'LV-ROOM-02', '探索房间 2', 'MAP_MAIN_001', 'ENT-ROOM-02', 2,
            '["COMBO-001"]'::jsonb,
            '["BRIDGE_OPEN"]'::jsonb,
            false, true,
            '{"config_status":"PROTOTYPE_PENDING_LEVEL_ART","mechanisms":["PLATFORM_BRIDGE"]}'::jsonb
        ),
        (
            'LV-ROOM-03', '探索房间 3', 'MAP_MAIN_001', 'ENT-ROOM-03', 3,
            '["COMBO-002"]'::jsonb,
            '["ENERGY_DOOR_OPEN"]'::jsonb,
            false, true,
            '{"config_status":"PROTOTYPE_PENDING_LEVEL_ART","mechanisms":["ENERGY_NODE","DOOR_BARRIER"]}'::jsonb
        ),
        (
            'LV-ROOM-04', '探索房间 4', 'MAP_MAIN_001', 'ENT-ROOM-04', 4,
            '["COMBO-003"]'::jsonb,
            '["MOVING_PLATFORM_LOCKED"]'::jsonb,
            false, true,
            '{"config_status":"PROTOTYPE_PENDING_LEVEL_ART","mechanisms":["MOVING_OBJECT","PLATFORM_BRIDGE"]}'::jsonb
        ),
        (
            'LV-ROOM-05', '探索房间 5', 'MAP_MAIN_001', 'ENT-ROOM-05', 5,
            '["COMBO-001","COMBO-002","COMBO-003"]'::jsonb,
            '["ROOM05_TARGET_A","ROOM05_TARGET_B"]'::jsonb,
            false, true,
            jsonb_build_object(
                'config_status', 'PROTOTYPE_PENDING_LEVEL_ART',
                'mechanism_count_min', 2
            )
        ),
        (
            'LV-HIDDEN-01', '隐藏结局', 'MAP_MAIN_001', 'ENT-HIDDEN-01', NULL,
            '["HIDDEN-ROUTE-01"]'::jsonb,
            '["ENDING_COMPLETE"]'::jsonb,
            true, true,
            '{"config_status":"PROTOTYPE_PENDING_HIDDEN_ROUTE_GATING","route_id":"HIDDEN-ROUTE-01"}'::jsonb
        )
        ON CONFLICT (level_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("level_enter_requests")
    op.drop_index("uq_level_runs_one_active_per_player", table_name="level_runs")
    op.drop_constraint("fk_level_runs_level", "level_runs", type_="foreignkey")
    op.drop_index("uq_levels_room_index", table_name="levels")
    op.drop_table("levels")
