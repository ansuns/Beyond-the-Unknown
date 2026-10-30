import sqlalchemy as sa
from alembic import op


revision = "0003_map_instance_members"
down_revision = "0002_seed_default_characters"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "map_instance_members",
        sa.Column(
            "player_id",
            sa.Uuid(),
            sa.ForeignKey("players.player_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "instance_id",
            sa.Uuid(),
            sa.ForeignKey("map_instances.instance_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("position_x", sa.Float(), nullable=False, server_default="0"),
        sa.Column("position_y", sa.Float(), nullable=False, server_default="0"),
        sa.Column("direction", sa.String(2), nullable=False, server_default="S"),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "direction IN ('N','NE','E','SE','S','SW','W','NW')",
            name="ck_map_member_direction",
        ),
    )
    op.create_index(
        "idx_map_instance_members_instance",
        "map_instance_members",
        ["instance_id", "last_seen_at"],
    )
    op.execute(
        """
        INSERT INTO maps (map_id, display_name, config, is_enabled)
        VALUES (
            'MAP_MAIN_001',
            '遗忘森林',
            jsonb_build_object(
                'config_version', 1,
                'config_status', 'PROTOTYPE_PENDING_MAP_ART',
                'coordinate_unit', 'prototype_logical_unit',
                'spawn_min_distance', 1.5,
                'spawn_points_pending_approval', true,
                'aoi_mode', 'FULL_INSTANCE_FALLBACK',
                'aoi_radius', NULL,
                'spawn_points',
                    (SELECT jsonb_agg(
                        jsonb_build_object(
                            'spawn_point_id', 'SPAWN_PROTO_' || lpad(n::text, 2, '0'),
                            'x', ((n - 1) % 5) * 2,
                            'y', ((n - 1) / 5) * 2
                        ) ORDER BY n
                    ) FROM generate_series(1, 20) AS g(n))
            ),
            true
        )
        ON CONFLICT (map_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("idx_map_instance_members_instance", table_name="map_instance_members")
    op.drop_table("map_instance_members")
    op.execute(
        """
        DELETE FROM maps
        WHERE map_id = 'MAP_MAIN_001'
          AND NOT EXISTS (
              SELECT 1 FROM map_instances
              WHERE map_instances.map_id = maps.map_id
          )
        """
    )
