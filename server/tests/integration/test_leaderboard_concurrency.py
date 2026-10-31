"""Leaderboard behaviour under concurrency and failure.

The single-threaded tests already cover the happy path. What actually breaks a
leaderboard in production is two recomputes racing, a recompute running while
scores arrive, or a rolled-back transaction leaving a half-built snapshot. Those
only appear with more than one connection, so these tests use SessionFactory
directly instead of the request client.
"""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.core.database import SessionFactory
from app.modules.progress.repository import recompute_leaderboard


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL and apply Alembic migrations for PostgreSQL integration tests",
)

BOARD = "EXPLORE"


async def create_season(season_id: str) -> None:
    async with SessionFactory() as session:
        async with session.begin():
            await session.execute(
                text("""
                    INSERT INTO seasons
                        (season_id, season_type, start_at_utc, end_at_utc,
                         status, settlement_status)
                    VALUES (:season_id, 'WEEKLY', '2001-01-01T00:00:00Z',
                            '2001-01-08T00:00:00Z', 'ACTIVE', 'PENDING')
                    ON CONFLICT (season_id) DO NOTHING
                """),
                {"season_id": season_id},
            )


async def seed_scores(season_id: str, scores: list[int]) -> list[str]:
    """One player per score, one ledger row each. Returns the player ids."""
    player_ids: list[str] = []
    async with SessionFactory() as session:
        async with session.begin():
            for index, score in enumerate(scores):
                row = await session.execute(
                    text("""
                        INSERT INTO players (wx_openid) VALUES (:openid)
                        ON CONFLICT (wx_openid) DO UPDATE SET wx_openid = EXCLUDED.wx_openid
                        RETURNING player_id
                    """),
                    {"openid": f"lb-{uuid4()}"},
                )
                player_id = row.scalar_one()
                player_ids.append(str(player_id))
                await session.execute(
                    text("""
                        INSERT INTO score_events
                            (player_id, board_type, period_id, delta, reason,
                             source_event_id, idempotency_key, created_at_utc)
                        VALUES (:player_id, :board, :season_id, :delta, 'EXP_DISCOVER',
                                :source, :key, now())
                    """),
                    {
                        "player_id": player_id,
                        "board": BOARD,
                        "season_id": season_id,
                        "delta": score,
                        "source": f"src-{uuid4()}",
                        "key": f"key-{uuid4()}",
                    },
                )
    return player_ids


async def snapshot(season_id: str) -> list[dict]:
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                text("""
                    SELECT player_id::text AS player_id, score, rank
                    FROM leaderboard_snapshots
                    WHERE season_id = :season_id AND board_type = :board
                    ORDER BY rank, player_id
                """),
                {"season_id": season_id, "board": BOARD},
            )
        ).mappings().all()
        return [dict(row) for row in rows]


async def ledger(season_id: str) -> list[dict]:
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                text("""
                    SELECT player_id::text AS player_id, delta, reason,
                           idempotency_key, created_at_utc
                    FROM score_events
                    WHERE period_id = :season_id AND board_type = :board
                    ORDER BY player_id, idempotency_key
                """),
                {"season_id": season_id, "board": BOARD},
            )
        ).mappings().all()
        return [dict(row) for row in rows]


async def recompute_once(season_id: str, apply: bool = True) -> dict:
    async with SessionFactory() as session:
        async with session.begin():
            return await recompute_leaderboard(session, season_id, BOARD, apply)


def test_concurrent_recompute_does_not_duplicate_or_lose_players() -> None:
    """Four recomputes at once must still leave one row per player, all correct."""

    async def scenario() -> None:
        season_id = f"WEEKLY-CONC-{uuid4().hex[:8]}"
        await create_season(season_id)
        player_ids = await seed_scores(season_id, [30, 10, 20, 20, 5])

        results = await asyncio.gather(
            *(recompute_once(season_id) for _ in range(4)),
            return_exceptions=True,
        )
        errors = [item for item in results if isinstance(item, Exception)]
        # The API deletes and rebuilds the board; concurrent runs may collide on
        # the same rows. Either they all succeed, or a collision surfaces as an
        # exception - what must never happen is silent duplicated or missing rows.
        rows = await snapshot(season_id)
        assert len(rows) == len(player_ids), f"rows={rows}, errors={errors[:1]}"
        assert len({row["player_id"] for row in rows}) == len(player_ids)
        assert sum(row["score"] for row in rows) == 85
        assert max(row["rank"] for row in rows) == 4

    asyncio.run(scenario())


def test_recompute_is_idempotent() -> None:
    async def scenario() -> None:
        season_id = f"WEEKLY-IDEM-{uuid4().hex[:8]}"
        await create_season(season_id)
        await seed_scores(season_id, [7, 3])

        first = await recompute_once(season_id)
        second = await recompute_once(season_id)
        assert first["applied"] is True
        # Nothing changed between the runs, so the second must report no work.
        assert second["applied"] is False
        assert second["difference_count"] == 0
        assert (await snapshot(season_id))[0]["score"] == 7

    asyncio.run(scenario())


def test_recompute_never_touches_the_ledger() -> None:
    """GDD 13.6: the ledger is the authority, snapshots are derived."""

    async def scenario() -> None:
        season_id = f"WEEKLY-LEDGER-{uuid4().hex[:8]}"
        await create_season(season_id)
        await seed_scores(season_id, [4, 9, 1])
        before = await ledger(season_id)

        await recompute_once(season_id)
        await recompute_once(season_id, apply=False)

        assert await ledger(season_id) == before

    asyncio.run(scenario())


def test_tied_scores_share_a_rank_and_order_is_stable() -> None:
    """The tie rule itself is LB-OQ-03 (undecided); sharing a rank is the current
    implementation and the response order must not shuffle between reads."""

    async def scenario() -> None:
        season_id = f"WEEKLY-TIE-{uuid4().hex[:8]}"
        await create_season(season_id)
        await seed_scores(season_id, [12, 12, 3])
        await recompute_once(season_id)

        first = await snapshot(season_id)
        second = await snapshot(season_id)
        assert first == second
        tied = [row for row in first if row["score"] == 12]
        assert len(tied) == 2
        assert tied[0]["rank"] == tied[1]["rank"] == 1
        assert first[-1]["rank"] == 2

    asyncio.run(scenario())


def test_rolled_back_recompute_leaves_the_previous_snapshot() -> None:
    """A failure after the DELETE must not leave the board empty."""

    async def scenario() -> None:
        season_id = f"WEEKLY-ROLLBACK-{uuid4().hex[:8]}"
        await create_season(season_id)
        await seed_scores(season_id, [6, 2])
        await recompute_once(season_id)
        good = await snapshot(season_id)
        assert len(good) == 2

        async with SessionFactory() as session:
            transaction = await session.begin()
            try:
                # Force a different ledger view, rebuild, then abandon the work.
                await session.execute(
                    text("""
                        UPDATE score_events SET delta = 100
                        WHERE period_id = :season_id AND board_type = :board
                    """),
                    {"season_id": season_id, "board": BOARD},
                )
                await recompute_leaderboard(session, season_id, BOARD, apply=True)
            finally:
                await transaction.rollback()

        assert await snapshot(season_id) == good
        assert sum(row["delta"] for row in await ledger(season_id)) == 8

    asyncio.run(scenario())
