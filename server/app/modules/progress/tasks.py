"""Personal task creation and reading (GDD 11.1).

Scope of this slice: the server creates the configured tasks for a player and
reports their objectives. Event-driven progress accumulation is the next slice
and is not claimed here - ``current_value`` starts at 0 and only changes once
that path lands.

The catalogue ships with the code rather than in docs, so the container image
can read it without mounting the repository.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CATALOG_PATH = Path(__file__).with_name("task_catalog.json")
STATUS_ACTIVE = "ACTIVE"
STATUS_COMPLETED = "COMPLETED"


@lru_cache(maxsize=1)
def load_task_catalog() -> tuple[dict[str, Any], ...]:
    """Return the task definitions. Cached: the file is packaged with the code."""
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise RuntimeError("task catalogue must contain at least one task")
    for task in tasks:
        if not task.get("task_id") or not task.get("objectives"):
            raise RuntimeError(f"task {task.get('task_id')!r} has no objectives")
    return tuple(tasks)


def _initial_progress(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_type": task["task_type"],
        "title": task.get("title", task["task_id"]),
        "objectives": [
            {
                "objective_id": objective["objective_id"],
                "objective_type": objective["objective_type"],
                "target_value": int(objective["target_value"]),
                "current_value": 0,
            }
            for objective in task["objectives"]
        ],
        "applied_events": [],
    }


async def ensure_player_tasks(session: AsyncSession, player_id: UUID) -> None:
    """Create any missing configured task for this player. Safe to repeat."""
    for task in load_task_catalog():
        await session.execute(
            text("""
                INSERT INTO player_tasks (player_id, task_id, status, progress)
                VALUES (:player_id, :task_id, :status, CAST(:progress AS jsonb))
                ON CONFLICT (player_id, task_id) DO NOTHING
            """),
            {
                "player_id": player_id,
                "task_id": task["task_id"],
                "status": STATUS_ACTIVE,
                "progress": json.dumps(_initial_progress(task), ensure_ascii=False),
            },
        )


def _is_complete(progress: dict[str, Any]) -> bool:
    objectives = progress.get("objectives") or []
    return bool(objectives) and all(
        int(objective.get("current_value", 0)) >= int(objective.get("target_value", 1))
        for objective in objectives
    )


async def list_player_tasks(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    """Return the player's tasks with their objectives and completion state."""
    await ensure_player_tasks(session, player_id)
    rows = (
        await session.execute(
            text("""
                SELECT task_id, status, progress, updated_at
                FROM player_tasks
                WHERE player_id = :player_id
                ORDER BY task_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()

    catalog = {task["task_id"]: task for task in load_task_catalog()}
    result = []
    for row in rows:
        progress = row["progress"] or {}
        status = row["status"]
        if status == STATUS_ACTIVE and _is_complete(progress):
            # Rule 5: every objective met means the task is done. Persisted so the
            # state does not depend on this read having happened.
            await session.execute(
                text("""
                    UPDATE player_tasks
                    SET status = :status, updated_at = now()
                    WHERE player_id = :player_id AND task_id = :task_id
                """),
                {
                    "status": STATUS_COMPLETED,
                    "player_id": player_id,
                    "task_id": row["task_id"],
                },
            )
            status = STATUS_COMPLETED
        known = catalog.get(row["task_id"])
        result.append(
            {
                "task_id": row["task_id"],
                "task_type": progress.get(
                    "task_type", known["task_type"] if known else None
                ),
                "title": progress.get(
                    "title", known.get("title") if known else row["task_id"]
                ),
                "status": status,
                "objectives": progress.get("objectives", []),
                "updated_at": row["updated_at"].isoformat(),
            }
        )
    return result
