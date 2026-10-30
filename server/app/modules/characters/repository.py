from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def list_player_characters(session: AsyncSession, player_id: UUID) -> dict[str, Any]:
    current = (
        await session.execute(
            text("SELECT current_character_id FROM players WHERE player_id = :player_id"),
            {"player_id": player_id},
        )
    ).scalar_one_or_none()
    rows = (
        await session.execute(
            text("""
                SELECT c.character_id, c.display_name, c.config, pc.unlocked_at
                FROM player_characters AS pc
                JOIN characters AS c ON c.character_id = pc.character_id
                WHERE pc.player_id = :player_id AND c.is_enabled = true
                ORDER BY c.character_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return {
        "current_character_id": current,
        "characters": [
            {
                "character_id": row["character_id"],
                "display_name": row["display_name"],
                "config": row["config"] or {},
                "unlocked_at": row["unlocked_at"].isoformat(),
                "is_unlocked": True,
            }
            for row in rows
        ],
    }


async def select_player_character(
    session: AsyncSession, player_id: UUID, character_id: str
) -> str | None:
    selected = (
        await session.execute(
            text("""
                UPDATE players AS p
                SET current_character_id = c.character_id, updated_at = now()
                FROM characters AS c
                JOIN player_characters AS pc
                  ON pc.character_id = c.character_id AND pc.player_id = :player_id
                WHERE p.player_id = :player_id
                  AND c.character_id = :character_id AND c.is_enabled = true
                RETURNING p.current_character_id
            """),
            {"player_id": player_id, "character_id": character_id},
        )
    ).scalar_one_or_none()
    await session.commit()
    return selected
