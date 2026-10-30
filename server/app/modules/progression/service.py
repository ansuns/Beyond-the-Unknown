import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def initialize_objectives(
    session: AsyncSession, player_id: UUID, run_id: UUID, level_id: str
) -> list[str]:
    objectives = (
        await session.execute(
            text("SELECT necessary_objectives FROM levels WHERE level_id = :level_id"),
            {"level_id": level_id},
        )
    ).scalar_one()
    for objective_id in objectives:
        await session.execute(
            text("""
                INSERT INTO level_objective_states (run_id, player_id, objective_id)
                VALUES (:run_id, :player_id, :objective_id)
                ON CONFLICT (run_id, player_id, objective_id) DO NOTHING
            """),
            {"run_id": run_id, "player_id": player_id, "objective_id": objective_id},
        )
    return list(objectives)


async def mark_objective_complete(
    session: AsyncSession,
    player_id: UUID,
    run_id: UUID,
    objective_id: str,
    source_event_id: str,
) -> bool:
    completed = (
        await session.execute(
            text("""
                INSERT INTO level_objective_states
                    (run_id, player_id, objective_id, status, source_event_id, completed_at)
                VALUES
                    (:run_id, :player_id, :objective_id, 'COMPLETED', :source_event_id, now())
                ON CONFLICT (run_id, player_id, objective_id) DO UPDATE
                SET status = 'COMPLETED',
                    source_event_id = EXCLUDED.source_event_id,
                    completed_at = COALESCE(
                        level_objective_states.completed_at, EXCLUDED.completed_at
                    ),
                    updated_at = now()
                WHERE level_objective_states.status <> 'COMPLETED'
                RETURNING objective_id
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "objective_id": objective_id,
                "source_event_id": source_event_id,
            },
        )
    ).scalar_one_or_none()
    return completed is not None


async def record_discovery(
    session: AsyncSession, player_id: UUID, run_id: UUID, discovery_id: str
) -> dict[str, Any]:
    discovery = (
        await session.execute(
            text("""
                SELECT discovery_type::text AS discovery_type, level_id,
                       location, related_rule
                FROM discovery_catalog
                WHERE discovery_id = :discovery_id AND is_enabled = true
            """),
            {"discovery_id": discovery_id},
        )
    ).mappings().one_or_none()
    if discovery is None:
        return {
            "discovery_id": discovery_id,
            "personal_first": False,
            "world_first": False,
            "collections": [],
        }

    inserted = (
        await session.execute(
            text("""
                INSERT INTO player_discoveries
                    (player_id, discovery_id, discovery_type, level_id, run_id,
                     location, related_rule)
                VALUES
                    (:player_id, :discovery_id, :discovery_type, :level_id,
                     :run_id, CAST(:location AS jsonb), :related_rule)
                ON CONFLICT (player_id, discovery_id) DO NOTHING
                RETURNING discovery_id
            """),
            {
                "player_id": player_id,
                "discovery_id": discovery_id,
                "discovery_type": discovery["discovery_type"],
                "level_id": discovery["level_id"],
                "run_id": run_id,
                "location": json.dumps(discovery["location"]),
                "related_rule": discovery["related_rule"],
            },
        )
    ).scalar_one_or_none()
    if inserted is None:
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
            "personal_first": False,
            "world_first": False,
            "collections": [],
        }

    world_first = (
        await session.execute(
            text("""
                INSERT INTO world_archive
                    (discovery_id, first_player_id, first_discovered_at, location, related_rule)
                VALUES (:discovery_id, :player_id, now(), CAST(:location AS jsonb), :related_rule)
                ON CONFLICT (discovery_id) DO NOTHING
                RETURNING discovery_id
            """),
            {
                "discovery_id": discovery_id,
                "player_id": player_id,
                "location": json.dumps(discovery["location"]),
                "related_rule": discovery["related_rule"],
            },
        )
    ).scalar_one_or_none() is not None

    collections = (
        await session.execute(
            text("""
                INSERT INTO player_collections
                    (player_id, collection_id, codex_category, source, source_id)
                SELECT :player_id, collection_id, codex_category, 'DISCOVERY', :discovery_id
                FROM collection_catalog
                WHERE source_discovery_id = :discovery_id AND is_enabled = true
                ON CONFLICT (player_id, collection_id) DO NOTHING
                RETURNING collection_id
            """),
            {"player_id": player_id, "discovery_id": discovery_id},
        )
    ).scalars().all()
    return {
        "discovery_id": discovery_id,
        "personal_first": True,
        "world_first": world_first,
        "collections": list(collections),
    }
