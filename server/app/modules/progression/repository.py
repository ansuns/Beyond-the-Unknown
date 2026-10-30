from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


class ProgressionRunNotFound(Exception):
    pass


class ProgressionRunNotActive(Exception):
    pass


class ObjectivesIncomplete(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing


class RewardNotClaimable(Exception):
    pass


class RewardNotFound(Exception):
    pass


class ProgressionIdempotencyConflict(Exception):
    pass


def _periods(now: datetime | None = None) -> list[dict[str, Any]]:
    settings = get_settings()
    try:
        zone = ZoneInfo(settings.server_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("SERVER_TIMEZONE must be a valid IANA timezone") from exc
    local_now = (now or datetime.now(UTC)).astimezone(zone)
    monday = (local_now - timedelta(days=local_now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    next_monday = monday + timedelta(days=7)
    month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    iso = local_now.isocalendar()
    return [
        {
            "season_id": f"W-{iso.year}-{iso.week:02d}",
            "season_type": "WEEKLY",
            "start": monday.astimezone(UTC),
            "end": next_monday.astimezone(UTC),
        },
        {
            "season_id": f"M-{local_now.year}-{local_now.month:02d}",
            "season_type": "MONTHLY",
            "start": month_start.astimezone(UTC),
            "end": next_month.astimezone(UTC),
        },
    ]


async def ensure_current_periods(
    session: AsyncSession, now: datetime | None = None
) -> list[dict[str, Any]]:
    periods = _periods(now)
    for period in periods:
        await session.execute(
            text("""
                INSERT INTO seasons
                    (season_id, season_type, start_at_utc, end_at_utc, status)
                VALUES
                    (:season_id, CAST(:season_type AS season_type),
                     :start_at, :end_at, 'ACTIVE')
                ON CONFLICT (season_id) DO NOTHING
            """),
            {
                "season_id": period["season_id"],
                "season_type": period["season_type"],
                "start_at": period["start"],
                "end_at": period["end"],
            },
        )
        await session.execute(
            text("""
                UPDATE seasons
                SET status = 'CLOSED'
                WHERE season_type = CAST(:season_type AS season_type)
                  AND season_id <> :season_id
                  AND status = 'ACTIVE'
            """),
            period,
        )
    return periods


async def _write_score_event(
    session: AsyncSession,
    player_id: UUID,
    board_type: str,
    reason: str,
    source_event_id: str,
    idempotency_key: str,
    run_id: UUID | None = None,
) -> list[dict[str, Any]]:
    rule = (
        await session.execute(
            text("""
                SELECT delta FROM score_rule_config
                WHERE board_type = :board_type AND reason = :reason
                  AND is_enabled = true AND delta > 0
            """),
            {"board_type": board_type, "reason": reason},
        )
    ).scalar_one_or_none()
    if rule is None:
        return []
    periods = await ensure_current_periods(session)
    written = []
    for period in periods:
        row = (
            await session.execute(
                text("""
                    INSERT INTO score_events
                        (player_id, board_type, period_id, delta, reason,
                         source_event_id, run_id, idempotency_key)
                    VALUES
                        (:player_id, CAST(:board_type AS board_type), :period_id,
                         :delta, :reason, :source_event_id, :run_id, :idempotency_key)
                    ON CONFLICT (board_type, period_id, idempotency_key) DO NOTHING
                    RETURNING event_id, period_id, delta
                """),
                {
                    "player_id": player_id,
                    "board_type": board_type,
                    "period_id": period["season_id"],
                    "delta": int(rule),
                    "reason": reason,
                    "source_event_id": source_event_id,
                    "run_id": run_id,
                    "idempotency_key": idempotency_key,
                },
            )
        ).mappings().one_or_none()
        if row is not None:
            written.append(dict(row))
    return written


async def record_discovery(
    session: AsyncSession,
    player_id: UUID,
    discovery_id: str,
    run_id: UUID | None = None,
) -> dict[str, Any]:
    catalog = (
        await session.execute(
            text("""
                SELECT discovery_id, discovery_type::text AS discovery_type,
                       level_id, location, related_rule, display_name
                FROM discovery_catalog
                WHERE discovery_id = :discovery_id AND is_enabled = true
            """),
            {"discovery_id": discovery_id},
        )
    ).mappings().one_or_none()
    if catalog is None:
        raise ValueError("Discovery is not configured or enabled")
    if run_id is not None:
        run = (
            await session.execute(
                text("""
                    SELECT level_id, status::text AS status
                    FROM level_runs
                    WHERE run_id = :run_id AND player_id = :player_id
                    FOR UPDATE
                """),
                {"run_id": run_id, "player_id": player_id},
            )
        ).mappings().one_or_none()
        if run is None or (catalog["level_id"] and run["level_id"] != catalog["level_id"]):
            raise ProgressionRunNotFound
        if run["status"] not in {"RUNNING", "COMPLETED"}:
            raise ProgressionRunNotActive

    personal = (
        await session.execute(
            text("""
                INSERT INTO player_discoveries
                    (player_id, discovery_id, discovery_type, level_id, run_id,
                     location, related_rule)
                VALUES
                    (:player_id, :discovery_id,
                     CAST(:discovery_type AS discovery_type), :level_id, :run_id,
                     CAST(:location AS jsonb), :related_rule)
                ON CONFLICT (player_id, discovery_id) DO NOTHING
                RETURNING first_discovered_at
            """),
            {
                "player_id": player_id,
                "discovery_id": discovery_id,
                "discovery_type": catalog["discovery_type"],
                "level_id": catalog["level_id"],
                "run_id": run_id,
                "location": json.dumps(catalog["location"]),
                "related_rule": catalog["related_rule"],
            },
        )
    ).mappings().one_or_none()
    if personal is None:
        await session.execute(
            text("""
                UPDATE player_discoveries
                SET trigger_count = trigger_count + 1
                WHERE player_id = :player_id AND discovery_id = :discovery_id
            """),
            {"player_id": player_id, "discovery_id": discovery_id},
        )
        return {
            "discovery_id": discovery_id,
            "is_personal_first": False,
            "is_world_first": False,
            "new_collections": [],
        }

    archive = (
        await session.execute(
            text("""
                INSERT INTO world_archive
                    (discovery_id, first_player_id, first_discovered_at,
                     location, related_rule)
                VALUES
                    (:discovery_id, :player_id, :first_at,
                     CAST(:location AS jsonb), :related_rule)
                ON CONFLICT (discovery_id) DO NOTHING
                RETURNING discovery_id
            """),
            {
                "discovery_id": discovery_id,
                "player_id": player_id,
                "first_at": personal["first_discovered_at"],
                "location": json.dumps(catalog["location"]),
                "related_rule": catalog["related_rule"],
            },
        )
    ).scalar_one_or_none()

    collection_rows = (
        await session.execute(
            text("""
                INSERT INTO player_collections
                    (player_id, collection_id, codex_category, source, source_id)
                SELECT :player_id, c.collection_id, c.codex_category,
                       'DISCOVERY', :discovery_id
                FROM collection_catalog AS c
                WHERE c.source_discovery_id = :discovery_id AND c.is_enabled = true
                ON CONFLICT (player_id, collection_id) DO NOTHING
                RETURNING collection_id
            """),
            {"player_id": player_id, "discovery_id": discovery_id},
        )
    ).scalars().all()

    await _write_score_event(
        session, player_id, "EXPLORE", "EXP_DISCOVER",
        discovery_id, f"discovery:{discovery_id}", run_id
    )
    for collection_id in collection_rows:
        await _write_score_event(
            session, player_id, "COLLECT", "COLLECT_NEW",
            collection_id, f"collection:{collection_id}", run_id
        )
    return {
        "discovery_id": discovery_id,
        "display_name": catalog["display_name"],
        "is_personal_first": True,
        "is_world_first": archive is not None,
        "new_collections": list(collection_rows),
    }


async def settle_level(
    session: AsyncSession,
    player_id: UUID,
    run_id: UUID,
    idempotency_key: str,
) -> dict[str, Any]:
    run = (
        await session.execute(
            text("""
                SELECT run_id, level_id, status::text AS status, started_at,
                       necessary_objectives
                FROM level_runs AS r
                JOIN levels AS l USING (level_id)
                WHERE r.run_id = :run_id AND r.player_id = :player_id
                FOR UPDATE OF r
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise ProgressionRunNotFound

    prior = (
        await session.execute(
            text("""
                SELECT result_id, level_id, result_status, completion_time_ms,
                       score_payload
                FROM settlements
                WHERE run_id = :run_id AND player_id = :player_id
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if prior is not None:
        if run["status"] != "COMPLETED":
            raise ProgressionRunNotActive
        return {
            "result_id": str(prior["result_id"]),
            "level_id": prior["level_id"],
            "result_status": prior["result_status"],
            "completion_time_ms": prior["completion_time_ms"],
            "score_payload": prior["score_payload"],
            "idempotent_replay": True,
        }
    if run["status"] != "RUNNING":
        raise ProgressionRunNotActive

    objectives = run["necessary_objectives"] or []
    if not objectives:
        raise ObjectivesIncomplete(["<missing-required-objectives-config>"])
    states = (
        await session.execute(
            text("""
                SELECT mechanism_config_id, state
                FROM mechanism_states
                WHERE run_id = :run_id AND player_id = :player_id
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().all()
    state_by_id = {row["mechanism_config_id"]: row["state"] for row in states}
    missing = []
    for objective in objectives:
        current = state_by_id.get(objective["mechanism_id"], {})
        if current.get("status") != objective["target_state"]:
            missing.append(objective["objective_id"])
    if missing:
        raise ObjectivesIncomplete(missing)

    ended_at = datetime.now(UTC)
    started_at = run["started_at"]
    elapsed_ms = max(0, int((ended_at - started_at).total_seconds() * 1000)) if started_at else None
    settlement = (
        await session.execute(
            text("""
                INSERT INTO settlements
                    (run_id, player_id, level_id, result_status,
                     completion_time_ms, score_payload, idempotency_key)
                VALUES
                    (:run_id, :player_id, :level_id, 'COMPLETED',
                     :completion_time_ms, '{}'::jsonb, :idempotency_key)
                RETURNING result_id
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "level_id": run["level_id"],
                "completion_time_ms": elapsed_ms,
                "idempotency_key": idempotency_key,
            },
        )
    ).mappings().one()
    await session.execute(
        text("""
            UPDATE level_runs
            SET status = 'COMPLETED', ended_at = :ended_at,
                completion_time_ms = :completion_time_ms, result_id = :result_id
            WHERE run_id = :run_id AND player_id = :player_id
        """),
        {
            "ended_at": ended_at,
            "completion_time_ms": elapsed_ms,
            "result_id": settlement["result_id"],
            "run_id": run_id,
            "player_id": player_id,
        },
    )
    await _write_score_event(
        session, player_id, "CLEAR", "CLEAR_STAGE",
        str(settlement["result_id"]), f"settlement:{run_id}", run_id
    )

    # Hidden ending discovery is derived only after the configured ending
    # objective is satisfied by authoritative mechanism state.
    if run["level_id"] == "LV-HIDDEN-01":
        await record_discovery(session, player_id, "DIS_ENDING", run_id)

    progress_version = (
        await session.execute(
            text("""
                UPDATE players
                SET progress_version = progress_version + 1, updated_at = now()
                WHERE player_id = :player_id
                RETURNING progress_version
            """),
            {"player_id": player_id},
        )
    ).scalar_one()
    completed = (
        await session.execute(
            text("""
                SELECT COALESCE(jsonb_agg(level_id ORDER BY level_id), '[]'::jsonb)
                FROM settlements
                WHERE player_id = :player_id AND result_status = 'COMPLETED'
            """),
            {"player_id": player_id},
        )
    ).scalar_one()
    progress = await get_progress_summary(session, player_id)
    await session.execute(
        text("""
            INSERT INTO progress_snapshots
                (player_id, progress_version, completed_level_ids, permanent_progress)
            VALUES (:player_id, :version, CAST(:completed AS jsonb),
                    CAST(:progress AS jsonb))
            ON CONFLICT (player_id, progress_version) DO NOTHING
        """),
        {
            "player_id": player_id,
            "version": progress_version,
            "completed": json.dumps(completed),
            "progress": json.dumps(progress),
        },
    )
    return {
        "result_id": str(settlement["result_id"]),
        "level_id": run["level_id"],
        "result_status": "COMPLETED",
        "completion_time_ms": elapsed_ms,
        "completion_score": 0,
        "score_payload": {"scoring_status": "PENDING_BALANCE_CONFIGURATION"},
        "progress_version": progress_version,
        "idempotent_replay": False,
    }


async def get_progress_summary(
    session: AsyncSession, player_id: UUID
) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
                SELECT
                  (SELECT count(*) FROM player_discoveries WHERE player_id = :player_id) AS discoveries,
                  (SELECT count(*) FROM player_collections WHERE player_id = :player_id) AS collections,
                  (SELECT count(*) FROM settlements WHERE player_id = :player_id
                    AND result_status = 'COMPLETED') AS completed_levels,
                  (SELECT count(*) FROM world_archive WHERE first_player_id = :player_id) AS world_firsts
            """),
            {"player_id": player_id},
        )
    ).mappings().one()
    return dict(row)


async def get_leaderboard(
    session: AsyncSession,
    player_id: UUID,
    board_type: str,
    season_type: str,
    limit: int = 50,
) -> dict[str, Any]:
    if board_type not in {"EXPLORE", "CLEAR", "COLLECT"}:
        raise ValueError("Invalid board type")
    if season_type not in {"WEEKLY", "MONTHLY"}:
        raise ValueError("Invalid season type")
    periods = await ensure_current_periods(session)
    period = next(item for item in periods if item["season_type"] == season_type)
    await session.flush()
    rows = (
        await session.execute(
            text("""
                WITH totals AS (
                  SELECT player_id, SUM(delta)::bigint AS score,
                         MIN(created_at_utc) AS first_score_at
                  FROM score_events
                  WHERE board_type = CAST(:board_type AS board_type)
                    AND period_id = :period_id
                  GROUP BY player_id
                ), ranked AS (
                  SELECT player_id, score,
                         RANK() OVER (ORDER BY score DESC) AS rank
                  FROM totals
                )
                SELECT player_id, score, rank
                FROM ranked
                ORDER BY rank ASC, player_id ASC
                LIMIT :limit
            """),
            {
                "board_type": board_type,
                "period_id": period["season_id"],
                "limit": limit,
            },
        )
    ).mappings().all()
    mine = (
        await session.execute(
            text("""
                SELECT score, rank FROM (
                  SELECT player_id, SUM(delta)::bigint AS score,
                         RANK() OVER (ORDER BY SUM(delta) DESC) AS rank
                  FROM score_events
                  WHERE board_type = CAST(:board_type AS board_type)
                    AND period_id = :period_id
                  GROUP BY player_id
                ) AS ranked
                WHERE player_id = :player_id
            """),
            {
                "board_type": board_type,
                "period_id": period["season_id"],
                "player_id": player_id,
            },
        )
    ).mappings().one_or_none()
    return {
        "board_type": board_type,
        "season_id": period["season_id"],
        "season_type": season_type,
        "start_at_utc": period["start"].isoformat(),
        "end_at_utc": period["end"].isoformat(),
        "entries": [
            {
                "player_id": str(row["player_id"]),
                "score": row["score"],
                "rank": row["rank"],
            }
            for row in rows
        ],
        "player_rank": (
            {"score": mine["score"], "rank": mine["rank"]}
            if mine is not None else None
        ),
        "ranking_policy": "PROVISIONAL_SHARED_RANK_TIE_POLICY_OPEN",
    }


async def list_player_rewards(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT pr.player_reward_id, pr.reward_id, r.reward_type::text AS reward_type,
                       r.reward_name, r.payload, pr.grant_mode::text AS grant_mode,
                       pr.status::text AS status, pr.source, pr.source_id,
                       pr.granted_at, pr.claimed_at
                FROM player_rewards AS pr
                JOIN rewards AS r ON r.reward_id = pr.reward_id
                WHERE pr.player_id = :player_id
                ORDER BY pr.granted_at DESC
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def claim_reward(
    session: AsyncSession, player_id: UUID, player_reward_id: UUID
) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
                UPDATE player_rewards
                SET status = 'OWNED', claimed_at = now()
                WHERE player_reward_id = :player_reward_id
                  AND player_id = :player_id
                  AND grant_mode = 'CLAIM'
                  AND status = 'PENDING_CLAIM'
                RETURNING player_reward_id, reward_id, status::text AS status, claimed_at
            """),
            {"player_reward_id": player_reward_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if row is None:
        exists = (
            await session.execute(
                text("""
                    SELECT 1 FROM player_rewards
                    WHERE player_reward_id = :player_reward_id
                      AND player_id = :player_id
                """),
                {"player_reward_id": player_reward_id, "player_id": player_id},
            )
        ).first()
        if exists is None:
            raise RewardNotFound
        raise RewardNotClaimable
    return dict(row)


async def get_player_discoveries(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT d.discovery_id, c.display_name, d.discovery_type::text AS discovery_type,
                       d.level_id, d.first_discovered_at, d.trigger_count,
                       (w.first_player_id = :player_id) AS is_world_first
                FROM player_discoveries AS d
                JOIN discovery_catalog AS c USING (discovery_id)
                LEFT JOIN world_archive AS w USING (discovery_id)
                WHERE d.player_id = :player_id
                ORDER BY d.first_discovered_at DESC
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def get_player_collections(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT c.collection_id, c.codex_category::text AS codex_category,
                       c.display_name, c.description, c.asset_id, c.sort_order,
                       p.source::text AS source, p.source_id, p.obtained_at
                FROM player_collections AS p
                JOIN collection_catalog AS c USING (collection_id)
                WHERE p.player_id = :player_id
                ORDER BY c.codex_category, c.sort_order, c.collection_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def get_world_archive(
    session: AsyncSession, limit: int = 50
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT w.discovery_id, d.display_name, d.discovery_type::text AS discovery_type,
                       '探索者-' || left(w.first_player_id::text, 8) AS first_player_label,
                       w.first_discovered_at, w.location, w.related_rule
                FROM world_archive AS w
                JOIN discovery_catalog AS d USING (discovery_id)
                ORDER BY w.first_discovered_at DESC
                LIMIT :limit
            """),
            {"limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def get_current_seasons(
    session: AsyncSession,
) -> list[dict[str, Any]]:
    periods = await ensure_current_periods(session)
    return [
        {
            "season_id": item["season_id"],
            "season_type": item["season_type"],
            "start_at_utc": item["start"].isoformat(),
            "end_at_utc": item["end"].isoformat(),
        }
        for item in periods
    ]
