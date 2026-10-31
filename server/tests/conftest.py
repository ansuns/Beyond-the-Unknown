"""Test-suite defaults so the suite is runnable without CI environment variables.

``app.main`` resolves its settings at import time and its lifespan starts the
Redis presence listener unless ``APP_ENV`` is ``test``. Tests that are meant to
run without PostgreSQL/Redis therefore only work when ``APP_ENV=test`` is
exported, which CI does but a clean checkout does not.

The default is applied with ``setdefault`` so an explicit override (for example
``APP_ENV=local`` while debugging) still wins.

The integration module also resets player-owned state once per session. See
``_reset_player_state`` for why the suite cannot rely on a clean database.
"""

import asyncio
import os

import pytest

os.environ.setdefault("APP_ENV", "test")

# Tables holding data that a test run creates. Catalogue and seed tables
# (levels, maps, characters, *_catalog, rewards, level_objectives) are inserted
# by Alembic migrations and must survive, so they are deliberately absent.
MUTABLE_TABLES = (
    "actions_log",
    "ad_reward_grants",
    "leaderboard_snapshots",
    "level_enter_requests",
    "level_run_positions",
    "level_runs",
    "map_instance_members",
    "map_instances",
    "mechanism_interaction_events",
    "mechanism_states",
    "player_achievements",
    "player_characters",
    "player_collections",
    "player_discoveries",
    "player_rewards",
    "player_rule_states",
    "player_tasks",
    "player_unlocked_hidden_routes",
    "player_unlocked_rules",
    "players",
    "progress_snapshots",
    "rule_cast_events",
    "score_events",
)


def _asyncpg_dsn(url: str) -> str:
    """Strip the SQLAlchemy driver suffix that asyncpg.connect rejects."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _truncate(dsn: str) -> None:
    import asyncpg

    connection = await asyncpg.connect(dsn=dsn)
    try:
        await connection.execute(
            "TRUNCATE TABLE " + ", ".join(MUTABLE_TABLES) + " RESTART IDENTITY CASCADE"
        )
    finally:
        await connection.close()


@pytest.fixture(scope="session", autouse=True)
def _reset_player_state() -> None:
    """Start every session from an empty player population.

    Integration tests assert on absolute counts -- "the second player to enter
    should see current_players == 2" -- but they share one long-lived database,
    so rows left by an earlier run make those assertions fail with counts that
    reflect history rather than the test. Truncating the mutable half keeps the
    migrations' seed data intact while giving each run the same starting point.
    """
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        return
    asyncio.run(_truncate(_asyncpg_dsn(url)))


@pytest.fixture
def tuned_rules():
    """Give the rule catalogue test values for the duration of one test.

    Production rows stay ``TUNING_REQUIRED`` so nothing here can be mistaken for
    an agreed design value; the fixture restores that state on the way out, even
    when the test fails.
    """
    from tests.support import apply_rule_tuning

    apply_rule_tuning(True)
    try:
        yield
    finally:
        apply_rule_tuning(False)
