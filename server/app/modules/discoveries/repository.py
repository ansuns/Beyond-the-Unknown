from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_player_discoveries(
    session: AsyncSession, player_id: UUID, limit: int, offset: int
) -> dict[str, Any]:
    rows = (
        await session.execute(
            text("""
                SELECT d.discovery_id, d.discovery_type::text AS discovery_type,
                       d.level_id, d.location, d.related_rule, d.display_name,
                       pd.first_discovered_at, pd.trigger_count
                FROM player_discoveries AS pd
                JOIN discovery_catalog AS d ON d.discovery_id = pd.discovery_id
                WHERE pd.player_id = :player_id
                ORDER BY pd.first_discovered_at DESC, d.discovery_id
                LIMIT :limit OFFSET :offset
            """),
            {"player_id": player_id, "limit": limit, "offset": offset},
        )
    ).mappings().all()
    return {
        "items": [
            {
                "discovery_id": row["discovery_id"],
                "discovery_type": row["discovery_type"],
                "level_id": row["level_id"],
                "location": row["location"],
                "related_rule": row["related_rule"],
                "display_name": row["display_name"],
                "first_discovered_at": row["first_discovered_at"].isoformat(),
                "trigger_count": int(row["trigger_count"]),
            }
            for row in rows
        ],
        "limit": limit,
        "offset": offset,
    }


async def list_player_collections(
    session: AsyncSession, player_id: UUID
) -> dict[str, Any]:
    rows = (
        await session.execute(
            text("""
                SELECT c.collection_id, c.codex_category::text AS codex_category,
                       c.display_name, c.description, c.asset_id, c.sort_order,
                       (pc.collection_id IS NOT NULL) AS is_collected,
                       pc.source::text AS source, pc.source_id, pc.obtained_at
                FROM collection_catalog AS c
                LEFT JOIN player_collections AS pc
                  ON pc.collection_id = c.collection_id
                 AND pc.player_id = :player_id
                WHERE c.is_enabled = true
                ORDER BY c.codex_category, c.sort_order, c.collection_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return {
        "items": [
            {
                "collection_id": row["collection_id"],
                "codex_category": row["codex_category"],
                "display_name": row["display_name"],
                "description": row["description"],
                "asset_id": row["asset_id"],
                "sort_order": int(row["sort_order"]),
                "is_collected": bool(row["is_collected"]),
                "source": row["source"],
                "source_id": row["source_id"],
                "obtained_at": row["obtained_at"].isoformat()
                if row["obtained_at"] is not None
                else None,
            }
            for row in rows
        ]
    }


async def get_exploration_summary(
    session: AsyncSession, player_id: UUID
) -> dict[str, Any]:
    row = (
        await session.execute(
            text("""
                SELECT
                    (SELECT count(*) FROM player_discoveries
                     WHERE player_id = :player_id) AS discovery_count,
                    (SELECT count(*) FROM player_collections
                     WHERE player_id = :player_id) AS collection_count,
                    (SELECT count(*) FROM world_archive
                     WHERE first_player_id = :player_id) AS world_first_count,
                    EXISTS (
                        SELECT 1 FROM player_discoveries
                        WHERE player_id = :player_id
                          AND discovery_type = 'DIS_ENDING'
                    ) AS hidden_ending_discovered
            """),
            {"player_id": player_id},
        )
    ).mappings().one()
    return {
        "discovery_count": int(row["discovery_count"]),
        "collection_count": int(row["collection_count"]),
        "world_first_count": int(row["world_first_count"]),
        "hidden_ending_discovered": bool(row["hidden_ending_discovered"]),
    }


async def list_world_archive(
    session: AsyncSession, limit: int, offset: int
) -> dict[str, Any]:
    rows = (
        await session.execute(
            text("""
                SELECT a.discovery_id, d.discovery_type::text AS discovery_type,
                       d.display_name, a.first_player_id, a.first_discovered_at,
                       a.location, a.related_rule
                FROM world_archive AS a
                JOIN discovery_catalog AS d ON d.discovery_id = a.discovery_id
                ORDER BY a.first_discovered_at, a.discovery_id
                LIMIT :limit OFFSET :offset
            """),
            {"limit": limit, "offset": offset},
        )
    ).mappings().all()
    return {
        "items": [
            {
                "discovery_id": row["discovery_id"],
                "discovery_type": row["discovery_type"],
                "display_name": row["display_name"],
                "first_player_id": str(row["first_player_id"]),
                "first_discovered_at": row["first_discovered_at"].isoformat(),
                "location": row["location"],
                "related_rule": row["related_rule"],
            }
            for row in rows
        ],
        "limit": limit,
        "offset": offset,
    }
