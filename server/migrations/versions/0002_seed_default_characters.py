from alembic import op

revision = "0002_seed_default_characters"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO characters (character_id, display_name, is_enabled, config)
        SELECT
            'CHR_' || lpad(n::text, 3, '0'),
            '角色 ' || lpad(n::text, 2, '0'),
            true,
            jsonb_build_object(
                'sort_order', n,
                'unlock_type', 'DEFAULT',
                'assets_pending', true,
                'portrait_asset_id', NULL,
                'model_asset_id', NULL,
                'animation_set_id', NULL,
                'preview_asset_id', NULL,
                'seed_version', 'vs1'
            )
        FROM generate_series(1, 12) AS n
        ON CONFLICT (character_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM characters AS c
        WHERE c.config ->> 'seed_version' = 'vs1'
          AND NOT EXISTS (
              SELECT 1 FROM player_characters AS pc
              WHERE pc.character_id = c.character_id
          )
    """)
