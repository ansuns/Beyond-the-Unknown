import math
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

MAIN_MAP_ID = "MAP_MAIN_001"


class MapConfigurationError(Exception):
    pass


async def _decrement_instance(session: AsyncSession, instance_id: UUID) -> None:
    await session.execute(
        text("""
            UPDATE map_instances
            SET current_players = GREATEST(current_players - 1, 0)
            WHERE instance_id = :instance_id
        """),
        {"instance_id": instance_id},
    )


async def _remove_expired_members(session: AsyncSession, grace_seconds: int) -> None:
    expired = (
        await session.execute(
            text("""
                DELETE FROM map_instance_members
                WHERE last_seen_at < now() - make_interval(secs => :grace_seconds)
                RETURNING instance_id
            """),
            {"grace_seconds": grace_seconds},
        )
    ).scalars().all()
    for instance_id in expired:
        await _decrement_instance(session, instance_id)


def _choose_spawn(
    spawn_points: list[dict[str, Any]],
    occupied: list[tuple[float, float]],
    minimum: float,
) -> dict[str, Any] | None:
    for point in spawn_points:
        x, y = float(point["x"]), float(point["y"])
        if all(math.dist((x, y), position) >= minimum for position in occupied):
            return point
    return None


async def enter_main_map(
    session: AsyncSession,
    player_id: UUID,
    max_players: int,
    reconnect_grace_seconds: int,
) -> tuple[dict[str, Any], bool]:
    await _remove_expired_members(session, reconnect_grace_seconds)
    await session.execute(
        text("SELECT player_id FROM players WHERE player_id = :player_id FOR UPDATE"),
        {"player_id": player_id},
    )

    existing = (
        await session.execute(
            text("""
                SELECT m.instance_id, m.session_id, m.position_x, m.position_y, m.direction,
                       mi.map_id, mi.status, mi.current_players, mi.max_players
                FROM map_instance_members AS m
                JOIN map_instances AS mi ON mi.instance_id = m.instance_id
                WHERE m.player_id = :player_id
                FOR UPDATE OF m, mi
            """),
            {"player_id": player_id},
        )
    ).mappings().one_or_none()
    if existing and existing["map_id"] == MAIN_MAP_ID and existing["status"] == "ACTIVE":
        await session.execute(
            text("""
                UPDATE map_instance_members SET last_seen_at = now()
                WHERE player_id = :player_id
            """),
            {"player_id": player_id},
        )
        await session.commit()
        return {
            "map_id": MAIN_MAP_ID,
            "instance_id": str(existing["instance_id"]),
            "session_id": str(existing["session_id"]),
            "spawn_position": {
                "x": float(existing["position_x"]),
                "y": float(existing["position_y"]),
                "direction": existing["direction"],
            },
            "current_players": int(existing["current_players"]),
            "max_players": int(existing["max_players"]),
            "reconnect_grace_seconds": reconnect_grace_seconds,
            "websocket_path": "/api/v1/ws/map",
        }, False
    if existing:
        await session.execute(
            text("DELETE FROM map_instance_members WHERE player_id = :player_id"),
            {"player_id": player_id},
        )
        await _decrement_instance(session, existing["instance_id"])

    map_row = (
        await session.execute(
            text("SELECT config FROM maps WHERE map_id = :map_id AND is_enabled = true"),
            {"map_id": MAIN_MAP_ID},
        )
    ).mappings().one_or_none()
    if map_row is None:
        raise MapConfigurationError("Main map is not configured")
    config = map_row["config"] or {}
    spawn_points = config.get("spawn_points") or []
    if not spawn_points:
        raise MapConfigurationError("Main map has no valid spawn points")
    min_distance = float(config.get("spawn_min_distance", 1.5))

    instance = (
        await session.execute(
            text("""
                SELECT instance_id, current_players, max_players
                FROM map_instances
                WHERE map_id = :map_id AND status = 'ACTIVE' AND current_players < max_players
                ORDER BY current_players ASC, created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """),
            {"map_id": MAIN_MAP_ID},
        )
    ).mappings().one_or_none()
    if instance is None:
        instance = (
            await session.execute(
                text("""
                    INSERT INTO map_instances
                        (map_id, shard_key, max_players, current_players, status)
                    VALUES (:map_id, :shard_key, :max_players, 0, 'ACTIVE')
                    RETURNING instance_id, current_players, max_players
                """),
                {
                    "map_id": MAIN_MAP_ID,
                    "shard_key": f"dev-{uuid4().hex}",
                    "max_players": max_players,
                },
            )
        ).mappings().one()

    occupied_rows = (
        await session.execute(
            text("""
                SELECT position_x, position_y FROM map_instance_members
                WHERE instance_id = :instance_id
            """),
            {"instance_id": instance["instance_id"]},
        )
    ).all()
    occupied = [(float(row[0]), float(row[1])) for row in occupied_rows]
    spawn = _choose_spawn(spawn_points, occupied, min_distance)
    if spawn is None:
        instance = (
            await session.execute(
                text("""
                    INSERT INTO map_instances
                        (map_id, shard_key, max_players, current_players, status)
                    VALUES (:map_id, :shard_key, :max_players, 0, 'ACTIVE')
                    RETURNING instance_id, current_players, max_players
                """),
                {
                    "map_id": MAIN_MAP_ID,
                    "shard_key": f"dev-{uuid4().hex}",
                    "max_players": max_players,
                },
            )
        ).mappings().one()
        spawn = spawn_points[0]

    session_id = uuid4()
    position_x, position_y = float(spawn["x"]), float(spawn["y"])
    current_players = (
        await session.execute(
            text("""
                UPDATE map_instances
                SET current_players = current_players + 1
                WHERE instance_id = :instance_id AND current_players < max_players
                RETURNING current_players
            """),
            {"instance_id": instance["instance_id"]},
        )
    ).scalar_one_or_none()
    if current_players is None:
        raise MapConfigurationError("Map instance reached capacity; retry entry")
    await session.execute(
        text("""
            INSERT INTO map_instance_members
                (player_id, instance_id, session_id, position_x, position_y, direction)
            VALUES (:player_id, :instance_id, :session_id, :x, :y, 'S')
        """),
        {
            "player_id": player_id,
            "instance_id": instance["instance_id"],
            "session_id": session_id,
            "x": position_x,
            "y": position_y,
        },
    )
    await session.commit()
    return {
        "map_id": MAIN_MAP_ID,
        "instance_id": str(instance["instance_id"]),
        "session_id": str(session_id),
        "spawn_position": {"x": position_x, "y": position_y, "direction": "S"},
        "current_players": int(current_players),
        "max_players": int(instance["max_players"]),
        "reconnect_grace_seconds": reconnect_grace_seconds,
        "websocket_path": "/api/v1/ws/map",
        "map_config_status": config.get("config_status", "UNKNOWN"),
    }, True


async def get_membership(
    session: AsyncSession, player_id: UUID, instance_id: UUID, session_id: UUID
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text("""
                SELECT m.instance_id, m.session_id, m.position_x, m.position_y, m.direction,
                       m.last_seen_at, p.status::text AS player_status, p.current_character_id,
                       mi.status AS instance_status, mi.map_id
                FROM map_instance_members AS m
                JOIN players AS p ON p.player_id = m.player_id
                JOIN map_instances AS mi ON mi.instance_id = m.instance_id
                WHERE m.player_id = :player_id AND m.instance_id = :instance_id
                  AND m.session_id = :session_id
            """),
            {"player_id": player_id, "instance_id": instance_id, "session_id": session_id},
        )
    ).mappings().one_or_none()
    return dict(row) if row is not None else None


async def touch_membership(session: AsyncSession, player_id: UUID, session_id: UUID) -> None:
    await session.execute(
        text("""
            UPDATE map_instance_members SET last_seen_at = now()
            WHERE player_id = :player_id AND session_id = :session_id
        """),
        {"player_id": player_id, "session_id": session_id},
    )
    await session.commit()


async def persist_position(
    session: AsyncSession,
    player_id: UUID,
    session_id: UUID,
    x: float,
    y: float,
    direction: str,
) -> bool:
    updated = (
        await session.execute(
            text("""
                UPDATE map_instance_members
                SET position_x = :x, position_y = :y, direction = :direction, last_seen_at = now()
                WHERE player_id = :player_id AND session_id = :session_id
                RETURNING player_id
            """),
            {
                "player_id": player_id,
                "session_id": session_id,
                "x": x,
                "y": y,
                "direction": direction,
            },
        )
    ).scalar_one_or_none()
    await session.commit()
    return updated is not None


async def mark_disconnected(
    session: AsyncSession, player_id: UUID, session_id: UUID, disconnected_at
) -> None:
    await session.execute(
        text("""
            UPDATE map_instance_members SET last_seen_at = :disconnected_at
            WHERE player_id = :player_id AND session_id = :session_id
        """),
        {
            "player_id": player_id,
            "session_id": session_id,
            "disconnected_at": disconnected_at,
        },
    )
    await session.commit()


async def remove_membership(
    session: AsyncSession, player_id: UUID, session_id: UUID
) -> UUID | None:
    instance_id = (
        await session.execute(
            text("""
                DELETE FROM map_instance_members
                WHERE player_id = :player_id AND session_id = :session_id
                RETURNING instance_id
            """),
            {"player_id": player_id, "session_id": session_id},
        )
    ).scalar_one_or_none()
    if instance_id is not None:
        await _decrement_instance(session, instance_id)
    await session.commit()
    return instance_id


async def expire_disconnected_membership(
    session: AsyncSession, player_id: UUID, session_id: UUID, disconnected_at
) -> UUID | None:
    instance_id = (
        await session.execute(
            text("""
                DELETE FROM map_instance_members
                WHERE player_id = :player_id AND session_id = :session_id
                  AND last_seen_at = :disconnected_at
                RETURNING instance_id
            """),
            {
                "player_id": player_id,
                "session_id": session_id,
                "disconnected_at": disconnected_at,
            },
        )
    ).scalar_one_or_none()
    if instance_id is not None:
        await _decrement_instance(session, instance_id)
    await session.commit()
    return instance_id
