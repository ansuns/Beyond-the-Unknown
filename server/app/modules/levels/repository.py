import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class LevelNotFound(Exception):
    pass


class LevelLocked(Exception):
    pass


class PlayerNotInMap(Exception):
    pass


class ActiveLevelRunExists(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class InvalidLevelRunState(Exception):
    pass


def _request_hash(level_id: str, entrance_id: str) -> str:
    payload = json.dumps(
        {"level_id": level_id, "entrance_id": entrance_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _level_payload(row: Any) -> dict[str, Any]:
    return {
        "level_id": row["level_id"],
        "level_name": row["level_name"],
        "entrance_id": row["entrance_id"],
        "room_index": row["room_index"],
        "target_duration_min": row["target_duration_min"],
        "target_duration_max": row["target_duration_max"],
        "hard_time_limit": row["hard_time_limit"],
        "time_limit_seconds": row["time_limit_seconds"],
        "repeatable": row["repeatable"],
        "repeat_reward_mode": row["repeat_reward_mode"],
        "required_laws": row["required_laws"],
        "necessary_objectives": row["necessary_objectives"],
        "config": row["config"],
        "is_hidden": row["is_hidden"],
        "is_unlocked": row.get("is_unlocked", not row["is_hidden"]),
    }


async def list_levels(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT l.level_id, l.level_name, l.entrance_id, l.room_index,
                       l.target_duration_min, l.target_duration_max, l.hard_time_limit,
                       l.time_limit_seconds, l.repeatable, l.repeat_reward_mode,
                       l.required_laws, l.necessary_objectives, l.config, l.is_hidden,
                       (
                           NOT l.is_hidden OR EXISTS (
                               SELECT 1
                               FROM hidden_routes AS h
                               JOIN player_unlocked_hidden_routes AS u
                                 ON u.hidden_route_id = h.hidden_route_id
                               WHERE u.player_id = :player_id
                                 AND h.result_level_id = l.level_id
                                 AND h.is_enabled = true
                                 AND h.config_status = 'READY'
                           )
                       ) AS is_unlocked
                FROM levels AS l
                WHERE l.is_enabled = true
                ORDER BY l.is_hidden ASC, l.room_index ASC NULLS LAST
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    result = []
    for row in rows:
        item = _level_payload(row)
        result.append(item)
    return result


async def enter_level(
    session: AsyncSession,
    player_id: UUID,
    level_id: str,
    entrance_id: str,
    idempotency_key: str,
) -> dict[str, Any]:
    request_hash = _request_hash(level_id, entrance_id)

    await session.execute(
        text("SELECT player_id FROM players WHERE player_id = :player_id FOR UPDATE"),
        {"player_id": player_id},
    )

    prior = (
        await session.execute(
            text("""
                SELECT r.run_id, r.instance_id, r.status::text AS run_status, r.level_id,
                       l.level_name, l.entrance_id, l.room_index,
                       l.target_duration_min, l.target_duration_max,
                       l.hard_time_limit, l.time_limit_seconds, l.repeatable,
                       l.repeat_reward_mode, l.required_laws, l.necessary_objectives,
                       l.config, l.is_hidden, q.request_hash
                FROM level_enter_requests AS q
                JOIN level_runs AS r ON r.run_id = q.run_id AND r.player_id = q.player_id
                JOIN levels AS l ON l.level_id = r.level_id
                WHERE q.player_id = :player_id AND q.idempotency_key = :idempotency_key
            """),
            {"player_id": player_id, "idempotency_key": idempotency_key},
        )
    ).mappings().one_or_none()
    if prior is not None:
        if prior["request_hash"] != request_hash:
            raise IdempotencyConflict
        return {
            "run_id": str(prior["run_id"]),
            "map_instance_id": None,
            "status": prior["run_status"],
            "level": _level_payload(prior),
            "idempotent_replay": True,
        }

    level = (
        await session.execute(
            text("""
                SELECT level_id, level_name, map_id, entrance_id, room_index,
                       target_duration_min, target_duration_max, hard_time_limit,
                       time_limit_seconds, repeatable, repeat_reward_mode,
                       required_laws, necessary_objectives, config, is_hidden
                FROM levels
                WHERE level_id = :level_id AND entrance_id = :entrance_id
                  AND is_enabled = true
                FOR SHARE
            """),
            {"level_id": level_id, "entrance_id": entrance_id},
        )
    ).mappings().one_or_none()
    if level is None:
        raise LevelNotFound
    if level["is_hidden"]:
        unlocked = (
            await session.execute(
                text("""
                    SELECT 1
                    FROM hidden_routes AS h
                    JOIN player_unlocked_hidden_routes AS u
                      ON u.hidden_route_id = h.hidden_route_id
                    WHERE u.player_id = :player_id
                      AND h.result_level_id = :level_id
                      AND h.is_enabled = true
                      AND h.config_status = 'READY'
                    LIMIT 1
                """),
                {"player_id": player_id, "level_id": level_id},
            )
        ).first()
        if unlocked is None:
            raise LevelLocked

    active_run = (
        await session.execute(
            text("""
                SELECT run_id FROM level_runs
                WHERE player_id = :player_id AND status IN ('CREATED','RUNNING')
                FOR UPDATE
            """),
            {"player_id": player_id},
        )
    ).scalar_one_or_none()
    if active_run is not None:
        raise ActiveLevelRunExists

    membership = (
        await session.execute(
            text("""
                SELECT m.instance_id, mi.map_id
                FROM map_instance_members AS m
                JOIN map_instances AS mi ON mi.instance_id = m.instance_id
                WHERE m.player_id = :player_id AND mi.status = 'ACTIVE'
                FOR UPDATE OF m, mi
            """),
            {"player_id": player_id},
        )
    ).mappings().one_or_none()
    if membership is None or membership["map_id"] != level["map_id"]:
        raise PlayerNotInMap

    run = (
        await session.execute(
            text("""
                INSERT INTO level_runs (player_id, level_id, instance_id, status)
                VALUES (:player_id, :level_id, :instance_id, 'CREATED')
                RETURNING run_id, status::text AS run_status
            """),
            {
                "player_id": player_id,
                "level_id": level_id,
                "instance_id": membership["instance_id"],
            },
        )
    ).mappings().one()

    removed = (
        await session.execute(
            text("""
                DELETE FROM map_instance_members
                WHERE player_id = :player_id
                RETURNING instance_id
            """),
            {"player_id": player_id},
        )
    ).scalar_one_or_none()
    if removed is not None:
        await session.execute(
            text("""
                UPDATE map_instances
                SET current_players = GREATEST(current_players - 1, 0)
                WHERE instance_id = :instance_id
            """),
            {"instance_id": removed},
        )

    await session.execute(
        text("""
            INSERT INTO level_enter_requests
                (player_id, idempotency_key, request_hash, run_id)
            VALUES (:player_id, :idempotency_key, :request_hash, :run_id)
        """),
        {
            "player_id": player_id,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "run_id": run["run_id"],
        },
    )
    await session.commit()
    return {
        "run_id": str(run["run_id"]),
        "map_instance_id": str(membership["instance_id"]),
        "status": run["run_status"],
        "level": _level_payload(level),
        "idempotent_replay": False,
    }


async def start_level(
    session: AsyncSession, player_id: UUID, run_id: UUID
) -> dict[str, Any]:
    run = (
        await session.execute(
            text("""
                SELECT run_id, level_id, status::text AS run_status, started_at, ended_at
                FROM level_runs
                WHERE run_id = :run_id AND player_id = :player_id
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise LevelNotFound
    if run["run_status"] == "CREATED":
        run = (
            await session.execute(
                text("""
                    UPDATE level_runs
                    SET status = 'RUNNING', started_at = now()
                    WHERE run_id = :run_id AND player_id = :player_id
                    RETURNING run_id, level_id, status::text AS run_status, started_at, ended_at
                """),
                {"run_id": run_id, "player_id": player_id},
            )
        ).mappings().one()
    elif run["run_status"] != "RUNNING":
        raise InvalidLevelRunState
    await session.commit()
    return {
        "run_id": str(run["run_id"]),
        "level_id": run["level_id"],
        "status": run["run_status"],
        "started_at": run["started_at"].isoformat() if run["started_at"] else None,
    }


async def abandon_level(
    session: AsyncSession, player_id: UUID, run_id: UUID
) -> dict[str, Any]:
    run = (
        await session.execute(
            text("""
                SELECT run_id, level_id, status::text AS run_status
                FROM level_runs
                WHERE run_id = :run_id AND player_id = :player_id
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise LevelNotFound
    if run["run_status"] in {"CREATED", "RUNNING"}:
        run = (
            await session.execute(
                text("""
                    UPDATE level_runs
                    SET status = 'ABANDONED', ended_at = now()
                    WHERE run_id = :run_id AND player_id = :player_id
                    RETURNING run_id, level_id, status::text AS run_status
                """),
                {"run_id": run_id, "player_id": player_id},
            )
        ).mappings().one()
    elif run["run_status"] != "ABANDONED":
        raise InvalidLevelRunState
    await session.commit()
    return {
        "run_id": str(run["run_id"]),
        "level_id": run["level_id"],
        "status": run["run_status"],
    }
