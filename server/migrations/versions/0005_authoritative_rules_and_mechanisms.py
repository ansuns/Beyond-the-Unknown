import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0005_authoritative_rules_and_mechanisms"
down_revision = "0004_levels_and_enter_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rule_catalog",
        sa.Column("rule_id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("duration_type", sa.String(32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(32), nullable=False),
        sa.Column("cooldown_ms", sa.Integer(), nullable=True),
        sa.Column("radius", sa.Float(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("allowed_target_types", JSONB(), nullable=False),
        sa.Column("config_status", sa.String(32), nullable=False, server_default="TUNING_REQUIRED"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("priority BETWEEN 1 AND 3", name="ck_rule_catalog_priority"),
        sa.CheckConstraint("cooldown_ms IS NULL OR cooldown_ms > 0", name="ck_rule_catalog_cooldown"),
        sa.CheckConstraint("radius IS NULL OR radius > 0", name="ck_rule_catalog_radius"),
        sa.CheckConstraint("duration_ms IS NULL OR duration_ms > 0", name="ck_rule_catalog_duration"),
        sa.CheckConstraint(
            "duration_type IN ('INSTANT','WHILE_CASTING','TIMED')",
            name="ck_rule_catalog_duration_type",
        ),
        sa.CheckConstraint(
            "scope_type IN ('POINT_RADIUS','OBJECT_RADIUS')",
            name="ck_rule_catalog_scope_type",
        ),
    )
    op.create_table(
        "combo_catalog",
        sa.Column("combo_id", sa.String(64), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("rule_ids", JSONB(), nullable=False),
        sa.Column("order_sensitive", sa.Boolean(), nullable=False),
        sa.Column("valid_order", JSONB(), nullable=True),
        sa.Column("time_window_ms", sa.Integer(), nullable=True),
        sa.Column("result_effect", sa.String(160), nullable=False),
        sa.Column("target_mechanism_id", sa.String(100), nullable=False),
        sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("config_status", sa.String(32), nullable=False, server_default="TUNING_REQUIRED"),
        sa.CheckConstraint("time_window_ms IS NULL OR time_window_ms > 0", name="ck_combo_time_window"),
        sa.CheckConstraint("jsonb_array_length(rule_ids) = 2", name="ck_combo_two_rules"),
    )
    op.create_table(
        "level_mechanism_catalog",
        sa.Column("level_id", sa.String(64), sa.ForeignKey("levels.level_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("mechanism_config_id", sa.String(100), primary_key=True),
        sa.Column("mechanism_type", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("initial_state", sa.String(24), nullable=False, server_default="INACTIVE"),
        sa.Column("target_state", sa.String(24), nullable=False, server_default="TRIGGERED"),
        sa.Column("trigger_rule", JSONB(), nullable=False, server_default="[]"),
        sa.Column("position_x", sa.Float(), nullable=True),
        sa.Column("position_y", sa.Float(), nullable=True),
        sa.Column("config", JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint(
            "initial_state IN ('INACTIVE','ACTIVE','LOCKED','TRIGGERED','COOLDOWN')",
            name="ck_level_mechanism_initial_state",
        ),
        sa.CheckConstraint(
            "target_state IN ('ACTIVE','LOCKED','TRIGGERED')",
            name="ck_level_mechanism_target_state",
        ),
    )
    op.create_table(
        "player_unlocked_rules",
        sa.Column("player_id", sa.Uuid(), sa.ForeignKey("players.player_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rule_id", sa.String(64), sa.ForeignKey("rule_catalog.rule_id"), primary_key=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="DEFAULT"),
        sa.Column("unlocked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("source IN ('DEFAULT','REWARD','EVENT')", name="ck_player_unlocked_rules_source"),
    )
    op.create_table(
        "player_rule_states",
        sa.Column("run_id", sa.Uuid(), primary_key=True),
        sa.Column("player_id", sa.Uuid(), primary_key=True),
        sa.Column("rule_id", sa.String(64), sa.ForeignKey("rule_catalog.rule_id"), primary_key=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_target_id", sa.String(100), nullable=True),
        sa.Column("active_effect", JSONB(), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_maintained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["run_id", "player_id"],
            ["level_runs.run_id", "level_runs.player_id"],
            ondelete="CASCADE",
            name="fk_player_rule_state_run_owner",
        ),
    )
    op.create_table(
        "rule_cast_events",
        sa.Column("event_id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("rule_id", sa.String(64), sa.ForeignKey("rule_catalog.rule_id"), nullable=False),
        sa.Column("target_id", sa.String(100), nullable=True),
        sa.Column("target_point", JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("result", JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["run_id", "player_id"],
            ["level_runs.run_id", "level_runs.player_id"],
            ondelete="CASCADE",
            name="fk_rule_cast_event_run_owner",
        ),
        sa.UniqueConstraint("run_id", "player_id", "idempotency_key", name="uq_rule_cast_idempotency"),
        sa.Index("idx_rule_cast_events_run_time", "run_id", "player_id", "created_at"),
    )

    op.execute(
        """
        INSERT INTO rule_catalog
            (rule_id, display_name, duration_type, priority, scope_type,
             cooldown_ms, radius, duration_ms, allowed_target_types, config_status)
        VALUES
            ('RULE_ECHO', '回声', 'INSTANT', 1, 'POINT_RADIUS',
             NULL, NULL, NULL,
             '["HIDDEN_OBJECT","MECHANISM"]'::jsonb, 'TUNING_REQUIRED'),
            ('RULE_GAZE', '注视', 'WHILE_CASTING', 2, 'OBJECT_RADIUS',
             NULL, NULL, NULL,
             '["PLATFORM","ENERGY_NODE","MECHANISM"]'::jsonb, 'TUNING_REQUIRED'),
            ('RULE_REVERSE', '逆流', 'TIMED', 3, 'OBJECT_RADIUS',
             NULL, NULL, NULL,
             '["ENERGY_NODE","PLATFORM","MOVING_OBJECT","MECHANISM"]'::jsonb, 'TUNING_REQUIRED')
        ON CONFLICT (rule_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO combo_catalog
            (combo_id, display_name, rule_ids, order_sensitive, valid_order,
             time_window_ms, result_effect, target_mechanism_id, is_hidden, config_status)
        VALUES
            ('COMBO-001', '回声·注视', '["RULE_ECHO","RULE_GAZE"]'::jsonb, true,
             '["RULE_ECHO","RULE_GAZE"]'::jsonb, NULL,
             'REVEAL_AND_MAINTAIN_BRIDGE', 'MECH_BRIDGE', false, 'TUNING_REQUIRED'),
            ('COMBO-002', '回声·逆流', '["RULE_ECHO","RULE_REVERSE"]'::jsonb, false,
             NULL, NULL, 'REVEAL_AND_REVERSE_ENERGY', 'MECH_ENERGY_GATE', false, 'TUNING_REQUIRED'),
            ('COMBO-003', '注视·逆流', '["RULE_GAZE","RULE_REVERSE"]'::jsonb, true,
             '["RULE_GAZE","RULE_REVERSE"]'::jsonb, NULL,
             'MAINTAIN_AND_REVERSE_PLATFORM', 'MECH_MOVING_PLATFORM', false, 'TUNING_REQUIRED')
        ON CONFLICT (combo_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO level_mechanism_catalog
            (level_id, mechanism_config_id, mechanism_type, target_type,
             initial_state, target_state, trigger_rule, config)
        VALUES
            ('LV-ROOM-01', 'MECH-ROOM01-HIDDEN-01', 'HIDEABLE', 'HIDDEN_OBJECT',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART","visible_by_default":false}'::jsonb),
            ('LV-ROOM-01', 'MECH-ROOM01-LIGHT-01', 'LIGHT_REVEAL', 'MECHANISM',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART"}'::jsonb),
            ('LV-ROOM-02', 'MECH_BRIDGE', 'PLATFORM_BRIDGE', 'PLATFORM',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT","COMBO_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART"}'::jsonb),
            ('LV-ROOM-03', 'MECH_ENERGY_GATE', 'ENERGY_NODE', 'ENERGY_NODE',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT","COMBO_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART","initial_direction":1}'::jsonb),
            ('LV-ROOM-04', 'MECH_MOVING_PLATFORM', 'MOVING_OBJECT', 'MOVING_OBJECT',
             'INACTIVE', 'TRIGGERED', '["RULE_EFFECT","COMBO_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART","initial_direction":1}'::jsonb),
            ('LV-ROOM-05', 'MECH-ROOM05-TARGET-A', 'PLATFORM_BRIDGE', 'PLATFORM',
             'INACTIVE', 'TRIGGERED', '["COMBO_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART"}'::jsonb),
            ('LV-ROOM-05', 'MECH-ROOM05-TARGET-B', 'ENERGY_NODE', 'ENERGY_NODE',
             'INACTIVE', 'TRIGGERED', '["COMBO_EFFECT"]'::jsonb,
             '{"config_status":"PENDING_POSITION_AND_ART","initial_direction":1}'::jsonb)
        ON CONFLICT (level_id, mechanism_config_id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO player_unlocked_rules (player_id, rule_id, source)
        SELECT p.player_id, r.rule_id, 'DEFAULT'
        FROM players AS p CROSS JOIN rule_catalog AS r
        WHERE r.is_enabled = true
        ON CONFLICT (player_id, rule_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("rule_cast_events")
    op.drop_table("player_rule_states")
    op.drop_table("player_unlocked_rules")
    op.drop_table("level_mechanism_catalog")
    op.drop_table("combo_catalog")
    op.drop_table("rule_catalog")
