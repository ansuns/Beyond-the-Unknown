from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.progress.repository import (
    _ensure_current_seasons,
    _refresh_leaderboard_snapshot,
    _snapshot_progress,
)


class SeasonNotFound(Exception):
    pass


class SeasonNotReviewable(Exception):
    pass


class SeasonReviewWindowOpen(Exception):
    pass


async def enqueue_due_seasons(
    session: AsyncSession, now: datetime | None = None
) -> int:
    current = now or datetime.now(UTC)
    await _ensure_current_seasons(session, current)
    due = (
        await session.execute(
            text("""
                SELECT season_id
                FROM seasons
                WHERE status = 'ACTIVE' AND end_at_utc <= :now
                ORDER BY end_at_utc
                FOR UPDATE SKIP LOCKED
            """),
            {"now": current},
        )
    ).scalars().all()
    count = 0
    for season_id in due:
        inserted = (
            await session.execute(
                text("""
                    INSERT INTO task_outbox
                        (task_type, schema_version, payload, idempotency_key)
                    VALUES
                        ('season.finalize', 1,
                         jsonb_build_object('season_id', :season_id),
                         :idempotency_key)
                    ON CONFLICT (idempotency_key) DO NOTHING
                    RETURNING task_id
                """),
                {
                    "season_id": season_id,
                    "idempotency_key": f"season-finalize:{season_id}",
                },
            )
        ).scalar_one_or_none()
        count += int(inserted is not None)
    return count


async def finalize_season(
    session: AsyncSession,
    season_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    season = (
        await session.execute(
            text("""
                SELECT season_id, season_type::text AS season_type,
                       status::text AS status, settlement_status,
                       end_at_utc
                FROM seasons
                WHERE season_id = :season_id
                FOR UPDATE
            """),
            {"season_id": season_id},
        )
    ).mappings().one_or_none()
    if season is None:
        raise SeasonNotFound
    if season["status"] in {"SETTLING", "SETTLED", "CLOSED"}:
        return {"season_id": season_id, "already_finalized": True}
    if season["status"] != "ACTIVE" or season["end_at_utc"] > current:
        raise SeasonNotReviewable

    for board_type in ("EXPLORE", "CLEAR", "COLLECT"):
        await _refresh_leaderboard_snapshot(session, season_id, board_type)

    review_until = current + timedelta(
        seconds=max(0, get_settings().season_review_window_seconds)
    )
    await session.execute(
        text("""
            UPDATE seasons
            SET status = 'SETTLING',
                settlement_status = 'REVIEW',
                review_until_utc = :review_until,
                reviewed_at_utc = NULL,
                reviewed_by = NULL,
                review_note = NULL
            WHERE season_id = :season_id
        """),
        {"season_id": season_id, "review_until": review_until},
    )
    await session.execute(
        text("""
            INSERT INTO task_outbox
                (task_type, schema_version, payload, idempotency_key,
                 available_at_utc)
            VALUES
                ('season.auto_approve', 1,
                 jsonb_build_object('season_id', :season_id),
                 :idempotency_key, :available_at)
            ON CONFLICT (idempotency_key) DO NOTHING
        """),
        {
            "season_id": season_id,
            "idempotency_key": f"season-auto-approve:{season_id}",
            "available_at": review_until,
        },
    )
    await session.execute(
        text("""
            INSERT INTO actions_log (action_type, payload)
            VALUES ('SEASON_FINALIZED',
                    jsonb_build_object('season_id', :season_id,
                                       'review_until_utc', :review_until))
        """),
        {"season_id": season_id, "review_until": review_until.isoformat()},
    )
    return {
        "season_id": season_id,
        "status": "SETTLING",
        "settlement_status": "REVIEW",
        "review_until_utc": review_until.isoformat(),
    }


async def _grant_season_rank_rewards(
    session: AsyncSession, season_id: str, season_type: str
) -> dict[str, int]:
    conditions = (
        await session.execute(
            text("""
                SELECT c.condition_id, c.condition_config, r.reward_id,
                       r.grant_mode::text AS grant_mode
                FROM reward_conditions AS c
                JOIN rewards AS r ON r.reward_id = c.reward_id
                WHERE c.trigger_type = 'SEASON_RANK'
                  AND c.is_enabled = true AND c.config_status = 'READY'
                  AND r.is_enabled = true AND r.is_paid = false
                  AND r.reward_type IN ('RT_APPEARANCE','RT_TITLE','RT_PET','RT_BADGE')
            """)
        )
    ).mappings().all()
    snapshots = (
        await session.execute(
            text("""
                SELECT board_type::text AS board_type, player_id, score, rank
                FROM leaderboard_snapshots
                WHERE season_id = :season_id
                ORDER BY board_type, rank, player_id
            """),
            {"season_id": season_id},
        )
    ).mappings().all()
    affected_players: set[Any] = set()
    grants = 0
    for condition in conditions:
        config = condition["condition_config"]
        if config.get("season_type") not in (None, "ANY", season_type):
            continue
        required_board = config.get("board_type")
        if required_board not in {"EXPLORE", "CLEAR", "COLLECT"}:
            continue
        try:
            rank_min = int(config.get("rank_min", 1))
            rank_max = int(config.get("rank_max", rank_min))
        except (TypeError, ValueError):
            continue
        if rank_min < 1 or rank_max < rank_min:
            continue
        for entry in snapshots:
            if (
                entry["board_type"] != required_board
                or not rank_min <= entry["rank"] <= rank_max
            ):
                continue
            source_id = f"{season_id}:{required_board}:{entry['player_id']}"
            key_material = (
                f"{season_id}:{required_board}:{entry['player_id']}:"
                f"{condition['condition_id']}:{condition['reward_id']}"
            )
            idempotency_key = "season:" + hashlib.sha256(
                key_material.encode("utf-8")
            ).hexdigest()
            status = (
                "PENDING_CLAIM"
                if condition["grant_mode"] == "CLAIM"
                else "OWNED"
            )
            inserted = (
                await session.execute(
                    text("""
                        INSERT INTO player_rewards
                            (player_id, reward_id, grant_mode, status, source,
                             source_id, idempotency_key)
                        VALUES
                            (:player_id, :reward_id, :grant_mode, :status,
                             'SEASON', :source_id, :idempotency_key)
                        ON CONFLICT DO NOTHING
                        RETURNING player_reward_id
                    """),
                    {
                        "player_id": entry["player_id"],
                        "reward_id": condition["reward_id"],
                        "grant_mode": condition["grant_mode"],
                        "status": status,
                        "source_id": source_id,
                        "idempotency_key": idempotency_key,
                    },
                )
            ).scalar_one_or_none()
            if inserted is not None:
                grants += 1
                affected_players.add(entry["player_id"])
    for player_id in affected_players:
        await _snapshot_progress(session, player_id)
    return {"granted": grants, "players": len(affected_players)}


async def review_season(
    session: AsyncSession,
    season_id: str,
    decision: str,
    reviewer: str,
    note: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if decision not in {"APPROVE", "REJECT"}:
        raise ValueError("Decision must be APPROVE or REJECT")
    current = now or datetime.now(UTC)
    season = (
        await session.execute(
            text("""
                SELECT season_id, season_type::text AS season_type,
                       status::text AS status, settlement_status,
                       review_until_utc
                FROM seasons
                WHERE season_id = :season_id
                FOR UPDATE
            """),
            {"season_id": season_id},
        )
    ).mappings().one_or_none()
    if season is None:
        raise SeasonNotFound
    if season["status"] != "SETTLING" or season["settlement_status"] != "REVIEW":
        raise SeasonNotReviewable

    if decision == "APPROVE":
        grants = await _grant_season_rank_rewards(
            session, season_id, season["season_type"]
        )
        status = "SETTLED"
        settlement_status = "APPROVED"
    else:
        grants = {"granted": 0, "players": 0}
        status = "CLOSED"
        settlement_status = "FAILED"

    await session.execute(
        text("""
            UPDATE seasons
            SET status = :status,
                settlement_status = :settlement_status,
                settled_at_utc = :now,
                reviewed_at_utc = :now,
                reviewed_by = :reviewer,
                review_note = :note
            WHERE season_id = :season_id
        """),
        {
            "status": status,
            "settlement_status": settlement_status,
            "now": current,
            "reviewer": reviewer[:96],
            "note": note[:512] if note else None,
            "season_id": season_id,
        },
    )
    await session.execute(
        text("""
            INSERT INTO actions_log (action_type, payload)
            VALUES (:action_type,
                    CAST(:payload AS jsonb))
        """),
        {
            "action_type": "SEASON_REVIEW_" + decision,
            "payload": json.dumps(
                {
                    "season_id": season_id,
                    "reviewer": reviewer[:96],
                    "note": note,
                    "granted_rewards": grants["granted"],
                }
            ),
        },
    )
    return {
        "season_id": season_id,
        "status": status,
        "settlement_status": settlement_status,
        "granted_rewards": grants["granted"],
        "affected_players": grants["players"],
    }


async def auto_approve_season(
    session: AsyncSession, season_id: str, now: datetime | None = None
) -> dict[str, Any]:
    current = now or datetime.now(UTC)
    season = (
        await session.execute(
            text("""
                SELECT status::text AS status, settlement_status,
                       review_until_utc
                FROM seasons
                WHERE season_id = :season_id
                FOR UPDATE
            """),
            {"season_id": season_id},
        )
    ).mappings().one_or_none()
    if season is None:
        raise SeasonNotFound
    if season["status"] != "SETTLING" or season["settlement_status"] != "REVIEW":
        return {"season_id": season_id, "auto_approved": False, "reason": "NOT_IN_REVIEW"}
    if season["review_until_utc"] and season["review_until_utc"] > current:
        next_attempt = season["review_until_utc"] + timedelta(seconds=2)
        await session.execute(
            text("""
                INSERT INTO task_outbox
                    (task_type, schema_version, payload, idempotency_key,
                     available_at_utc)
                VALUES
                    ('season.auto_approve', 1,
                     jsonb_build_object('season_id', :season_id),
                     :idempotency_key, :available_at)
                ON CONFLICT (idempotency_key) DO NOTHING
            """),
            {
                "season_id": season_id,
                "idempotency_key": (
                    f"season-auto-approve:{season_id}:"
                    f"{season['review_until_utc'].isoformat()}"
                ),
                "available_at": next_attempt,
            },
        )
        return {
            "season_id": season_id,
            "auto_approved": False,
            "reason": "REVIEW_WINDOW_OPEN",
            "retry_at_utc": next_attempt.isoformat(),
        }
    result = await review_season(
        session,
        season_id,
        "APPROVE",
        "AUTO_REVIEW_TIMEOUT",
        "Automatically approved after the configured review window.",
        current,
    )
    return {**result, "auto_approved": True}
