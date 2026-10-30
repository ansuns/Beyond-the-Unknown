from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class PlayerBannedError(Exception):
    pass


async def get_or_create_player(session: AsyncSession, openid_digest: str) -> tuple[dict[str, Any], bool]:
    async with session.begin():
        inserted = (
            await session.execute(
                text("""
                    INSERT INTO players (wx_openid) VALUES (:openid)
                    ON CONFLICT (wx_openid) DO NOTHING
                    RETURNING player_id, current_character_id, progress_version, status::text AS status
                """),
                {"openid": openid_digest},
            )
        ).mappings().one_or_none()
        is_new_player = inserted is not None
        if inserted is None:
            row = (
                await session.execute(
                    text("""
                        SELECT player_id, current_character_id, progress_version, status::text AS status
                        FROM players WHERE wx_openid = :openid
                    """),
                    {"openid": openid_digest},
                )
            ).mappings().one()
        else:
            row = inserted
            await session.execute(
                text("""
                    INSERT INTO player_characters (player_id, character_id, source)
                    SELECT :player_id, character_id, 'DEFAULT'
                    FROM characters WHERE is_enabled = true
                    ON CONFLICT (player_id, character_id) DO NOTHING
                """),
                {"player_id": row["player_id"]},
            )
        if row["status"] != "NORMAL":
            raise PlayerBannedError
        return {
            "player_id": UUID(str(row["player_id"])),
            "current_character_id": row["current_character_id"],
            "progress_version": int(row["progress_version"]),
        }, is_new_player
