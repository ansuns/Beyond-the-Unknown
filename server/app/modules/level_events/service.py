"""Delivery of room gameplay events to tasks and to the player's socket.

The three sources share one path so a future event cannot be wired to tasks but
forget the socket, or vice versa. Failure policy differs per source on purpose:

* LOGIN must never break authentication. It runs after the player is already
  created and commits on its own, so a progress failure is logged and dropped.
* MOVE and RULE_CAST run inside the request that already owns the gameplay
  transaction. They must not be swallowed: if the objective cannot be advanced
  the whole request fails and the client retries, because a move that was
  accepted but not recorded is worse than a rejected move.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.level_events.events import LevelEvent
from app.modules.progress.tasks import ensure_player_tasks, record_task_event
from app.realtime.manager import map_connections

logger = logging.getLogger(__name__)

EVENT_COMMAND = "LEVEL_EVENT"


async def active_instance_id(session: AsyncSession, player_id: UUID) -> str | None:
    """Find the map instance the player is currently present in, if any.

    A player can be mid-run without a live socket (offline progress, or the app
    was killed). Returning ``None`` is normal: the event still counts, it is
    simply not delivered to anyone.
    """
    row = (
        await session.execute(
            text("""
                SELECT instance_id
                FROM map_instance_members
                WHERE player_id = :player_id
                ORDER BY last_seen_at DESC
                LIMIT 1
            """),
            {"player_id": player_id},
        )
    ).first()
    return str(row[0]) if row is not None else None


async def publish_level_event(
    session: AsyncSession,
    event: LevelEvent,
    *,
    deliver: bool = True,
) -> dict[str, Any]:
    """Advance matching task objectives and notify the player's connections.

    Idempotency comes from ``record_task_event``: the applied key is stored on
    the task row and the row is locked, so a duplicate report advances nothing.
    This function is therefore safe to call on every retry and every duplicate
    position packet.
    """
    advanced = await record_task_event(
        session, event.player_id, event.type.value, event.source_id
    )

    delivered = False
    if deliver:
        instance_id = await active_instance_id(session, event.player_id)
        if instance_id is not None:
            await map_connections.send_to_player(
                instance_id,
                str(event.player_id),
                EVENT_COMMAND,
                event.to_message(),
            )
            delivered = True

    return {
        "event": event.type.value,
        "source_id": event.source_id,
        "advanced_tasks": advanced,
        "delivered": delivered,
    }


async def record_login_event(session: AsyncSession, player_id: UUID) -> None:
    """Best-effort LOGIN handling for the authentication path.

    Tasks are created here rather than lazily on the first progress read, because
    a player who logs in and closes the app should still have their tutorial
    task waiting with the first objective already met.
    """
    from app.modules.level_events.events import login_event

    try:
        await ensure_player_tasks(session, player_id)
        await publish_level_event(session, login_event(player_id), deliver=False)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("LOGIN event failed player_id=%s", player_id)
