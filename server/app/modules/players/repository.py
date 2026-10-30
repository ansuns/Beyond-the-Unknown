from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_player_profile(session: AsyncSession, player_id: UUID) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text("""
                SELECT player_id, current_character_id, progress_version, status::text AS status,
                       created_at, updated_at
                FROM players WHERE player_id = :player_id
            """),
            {"player_id": player_id},
        )
    ).mappings().one_or_none()
    if row is None:
        return None
    return {
        "player_id": str(row["player_id"]),
        "current_character_id": row["current_character_id"],
        "progress_version": int(row["progress_version"]),
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }
