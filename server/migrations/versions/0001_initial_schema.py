from pathlib import Path

from alembic import op

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    sql_path = Path(__file__).resolve().parents[2] / "schema" / "0001_initial_schema.sql"
    source = sql_path.read_text(encoding="utf-8")
    # The source is plain DDL without procedural blocks; remove comments and transaction
    # wrappers, then execute one PostgreSQL statement at a time through Alembic.
    source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("--"))
    source = source.replace("BEGIN;", "").replace("COMMIT;", "")
    for statement in source.split(";"):
        statement = statement.strip()
        if statement:
            op.execute(statement)


def downgrade() -> None:
    for table in (
        "actions_log", "ad_reward_grants", "settlements", "progress_snapshots",
        "player_tasks", "player_achievements", "achievements", "player_rewards",
        "rewards", "leaderboard_snapshots", "score_events", "seasons", "world_archive",
        "player_collections", "player_discoveries", "collection_catalog",
        "discovery_catalog", "mechanism_states", "level_runs", "map_instances",
        "maps", "player_characters", "players", "characters", "schema_migrations",
    ):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
    for enum_name in (
        "ad_reward_type", "collection_source", "codex_category", "discovery_type",
        "achievement_status", "player_reward_status", "grant_mode", "reward_type",
        "season_status", "season_type", "board_type", "level_run_status", "player_status",
    ):
        op.execute(f'DROP TYPE IF EXISTS "{enum_name}" CASCADE')
