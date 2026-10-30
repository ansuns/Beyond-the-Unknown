import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.progression.score_service import award_score_if_configured
from app.modules.progression.service import record_discovery


class SettlementRunNotFound(Exception):
    pass


class IncompleteObjectives(Exception):
    def __init__(self, missing: list[str]):
        self.missing = missing


class SettlementConflict(Exception):
    pass


async def _unlock_hidden_route(
    session: AsyncSession, player_id: UUID, run_id: UUID
) -> bool:
    route = (
        await session.execute(
            text("""
                SELECT route_id, prerequisite_levels, trigger_combos,
                       trigger_mechanisms, result_level_id
                FROM hidden_route_catalog
                WHERE route_id = 'HIDDEN-ROUTE-01'
                  AND is_enabled = true AND config_status = 'READY'
            """)
        )
    ).mappings().one_or_none()
    if route is None:
        return False

    completed = (
        await session.execute(
            text("""
                SELECT DISTINCT level_id FROM settlements
                WHERE player_id = :player_id AND result_status = 'COMPLETED'
                  AND level_id = ANY(:level_ids)
            """),
            {"player_id": player_id, "level_ids": route["prerequisite_levels"]},
        )
    ).scalars().all()
    if set(completed) != set(route["prerequisite_levels"]):
        return False

    rows = (
        await session.execute(
            text("""
                SELECT result->'combo'->>'combo_id' AS combo_id,
                       result->'combo'->>'mechanism_id' AS mechanism_id
                FROM rule_cast_events
                WHERE run_id = :run_id
                  AND result->'combo' IS NOT NULL
                  AND result->'combo' <> 'null'::jsonb
                ORDER BY created_at ASC
            """),
            {"run_id": run_id},
        )
    ).mappings().all()
    sequence = []
    seen = set()
    for row in rows:
        combo_id = row["combo_id"]
        if combo_id and combo_id not in seen:
            sequence.append((combo_id, row["mechanism_id"]))
            seen.add(combo_id)
    expected = list(zip(route["trigger_combos"], route["trigger_mechanisms"], strict=True))
    if sequence[: len(expected)] != expected:
        return False

    unlocked = (
        await session.execute(
            text("""
                INSERT INTO player_hidden_routes (player_id, route_id, source_run_id)
                VALUES (:player_id, :route_id, :run_id)
                ON CONFLICT (player_id, route_id) DO NOTHING
                RETURNING route_id
            """),
            {"player_id": player_id, "route_id": route["route_id"], "run_id": run_id},
        )
    ).scalar_one_or_none()
    if unlocked is None:
        return False

    await session.execute(
        text("""
            INSERT INTO mechanism_states
                (run_id, player_id, mechanism_config_id, mechanism_type, state)
            VALUES
                (:run_id, :player_id, 'M05-HIDDEN-GATE', 'HIDDEN_GATE',
                 '{"status":"TRIGGERED","route_id":"HIDDEN-ROUTE-01"}'::jsonb)
            ON CONFLICT (run_id, mechanism_config_id) DO UPDATE
            SET state = EXCLUDED.state, updated_at = now()
        """),
        {"run_id": run_id, "player_id": player_id},
    )
    await record_discovery(session, player_id, run_id, "DISC-HIDDEN-ROUTE-01")
    return True


async def settle_level(
    session: AsyncSession,
    player_id: UUID,
    run_id: UUID,
    idempotency_key: str,
) -> dict[str, Any]:
    player = (
        await session.execute(
            text("SELECT progress_version FROM players WHERE player_id = :player_id FOR UPDATE"),
            {"player_id": player_id},
        )
    ).mappings().one_or_none()
    if player is None:
        raise SettlementRunNotFound

    run = (
        await session.execute(
            text("""
                SELECT run_id, level_id, status::text AS run_status, started_at
                FROM level_runs
                WHERE run_id = :run_id AND player_id = :player_id
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise SettlementRunNotFound

    existing = (
        await session.execute(
            text("""
                SELECT result_id, run_id, player_id, level_id, result_status,
                       completion_time_ms, score_payload, idempotency_key
                FROM settlements WHERE run_id = :run_id
            """),
            {"run_id": run_id},
        )
    ).mappings().one_or_none()
    if existing is not None:
        await session.commit()
        return {
            "result_id": str(existing["result_id"]),
            "run_id": str(existing["run_id"]),
            "level_id": existing["level_id"],
            "status": existing["result_status"],
            "completion_time_ms": existing["completion_time_ms"],
            "score": existing["score_payload"],
            "idempotent_replay": True,
        }

    key_owner = (
        await session.execute(
            text("SELECT run_id FROM settlements WHERE idempotency_key = :key"),
            {"key": idempotency_key},
        )
    ).scalar_one_or_none()
    if key_owner is not None and key_owner != run_id:
        raise SettlementConflict
    if run["run_status"] != "RUNNING":
        raise SettlementConflict

    level = (
        await session.execute(
            text("""
                SELECT necessary_objectives
                FROM levels WHERE level_id = :level_id AND is_enabled = true
            """),
            {"level_id": run["level_id"]},
        )
    ).mappings().one()
    required = list(level["necessary_objectives"] or [])
    completed = (
        await session.execute(
            text("""
                SELECT objective_id FROM level_objective_states
                WHERE run_id = :run_id AND player_id = :player_id
                  AND status = 'COMPLETED'
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).scalars().all()
    missing = sorted(set(required) - set(completed))
    if not required or missing:
        raise IncompleteObjectives(missing or ["NO_REQUIRED_OBJECTIVES_CONFIGURED"])

    now = datetime.now(UTC)
    elapsed_ms = (
        max(0, int((now - run["started_at"]).total_seconds() * 1000))
        if run["started_at"] is not None
        else None
    )
    discovery_ids = (
        await session.execute(
            text("""
                SELECT discovery_id FROM player_discoveries
                WHERE player_id = :player_id AND run_id = :run_id
                ORDER BY first_discovered_at
            """),
            {"player_id": player_id, "run_id": run_id},
        )
    ).scalars().all()
    collection_ids = (
        await session.execute(
            text("""
                SELECT DISTINCT pc.collection_id
                FROM player_collections AS pc
                JOIN collection_catalog AS cc ON cc.collection_id = pc.collection_id
                WHERE pc.player_id = :player_id
                  AND pc.source = 'DISCOVERY'
                  AND pc.source_id = ANY(:discovery_ids)
                ORDER BY pc.collection_id
            """),
            {"player_id": player_id, "discovery_ids": discovery_ids or [""]},
        )
    ).scalars().all()
    initial_score = {
        "completion_score": None,
        "score_status": "TUNING_REQUIRED",
        "score_awards": [],
    }
    result = (
        await session.execute(
            text("""
                INSERT INTO settlements
                    (run_id, player_id, level_id, result_status,
                     completion_time_ms, score_payload, idempotency_key)
                VALUES
                    (:run_id, :player_id, :level_id, 'COMPLETED',
                     :completion_time_ms, CAST(:score_payload AS jsonb), :idempotency_key)
                RETURNING result_id
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "level_id": run["level_id"],
                "completion_time_ms": elapsed_ms,
                "score_payload": json.dumps(initial_score),
                "idempotency_key": idempotency_key,
            },
        )
    ).mappings().one()
    result_id = result["result_id"]

    await session.execute(
        text("""
            UPDATE level_runs
            SET status = 'COMPLETED', ended_at = :ended_at,
                completion_time_ms = :completion_time_ms, result_id = :result_id
            WHERE run_id = :run_id AND player_id = :player_id
        """),
        {
            "ended_at": now,
            "completion_time_ms": elapsed_ms,
            "result_id": result_id,
            "run_id": run_id,
            "player_id": player_id,
        },
    )

    score_awards = await award_score_if_configured(
        session, player_id, "CLEAR_STAGE", str(result_id), run_id
    )
    score_payload = {
        "completion_score": sum(item["delta"] for item in score_awards)
        if score_awards
        else None,
        "score_status": "READY" if score_awards else "TUNING_REQUIRED",
        "score_awards": score_awards,
        "discoveries": list(discovery_ids),
        "collections": list(collection_ids),
    }
    await session.execute(
        text("UPDATE settlements SET score_payload = CAST(:payload AS jsonb) WHERE result_id = :result_id"),
        {"payload": json.dumps(score_payload), "result_id": result_id},
    )

    snapshot = (
        await session.execute(
            text("""
                SELECT completed_level_ids, permanent_progress
                FROM progress_snapshots
                WHERE player_id = :player_id
                ORDER BY progress_version DESC LIMIT 1
            """),
            {"player_id": player_id},
        )
    ).mappings().one_or_none()
    completed_levels = list(snapshot["completed_level_ids"]) if snapshot else []
    if run["level_id"] not in completed_levels:
        completed_levels.append(run["level_id"])
    permanent = dict(snapshot["permanent_progress"]) if snapshot else {}
    permanent["discovery_count"] = (
        await session.execute(
            text("SELECT count(*) FROM player_discoveries WHERE player_id = :player_id"),
            {"player_id": player_id},
        )
    ).scalar_one()
    permanent["collection_count"] = (
        await session.execute(
            text("SELECT count(*) FROM player_collections WHERE player_id = :player_id"),
            {"player_id": player_id},
        )
    ).scalar_one()

    next_version = int(player["progress_version"]) + 1
    await session.execute(
        text("""
            UPDATE players SET progress_version = :version, updated_at = now()
            WHERE player_id = :player_id
        """),
        {"version": next_version, "player_id": player_id},
    )

    hidden_unlocked = False
    if run["level_id"] == "LV-ROOM-05":
        hidden_unlocked = await _unlock_hidden_route(session, player_id, run_id)
        if hidden_unlocked:
            permanent["hidden_routes"] = ["HIDDEN-ROUTE-01"]

    await session.execute(
        text("""
            INSERT INTO progress_snapshots
                (player_id, progress_version, completed_level_ids, permanent_progress)
            VALUES (:player_id, :version, CAST(:completed AS jsonb), CAST(:permanent AS jsonb))
        """),
        {
            "player_id": player_id,
            "version": next_version,
            "completed": json.dumps(completed_levels),
            "permanent": json.dumps(permanent),
        },
    )

    if run["level_id"] == "LV-HIDDEN-01":
        await record_discovery(session, player_id, run_id, "DISC-ENDING-G009")
    await session.commit()
    return {
        "result_id": str(result_id),
        "run_id": str(run_id),
        "level_id": run["level_id"],
        "status": "COMPLETED",
        "completion_time_ms": elapsed_ms,
        "discoveries": list(discovery_ids),
        "collections": list(collection_ids),
        "score": score_payload,
        "hidden_route_unlocked": hidden_unlocked,
        "progress_version": next_version,
        "idempotent_replay": False,
    }
