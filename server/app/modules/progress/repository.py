import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings


class SettlementRunNotFound(Exception):
    pass


class SettlementStateConflict(Exception):
    pass


class SettlementConfigIncomplete(Exception):
    pass


class IncompleteObjectives(Exception):
    def __init__(self, objective_ids: list[str]):
        self.objective_ids = objective_ids


class SettlementIdempotencyConflict(Exception):
    pass


class LeaderboardSeasonNotFound(Exception):
    pass


class RewardNotFound(Exception):
    pass


class RewardNotClaimable(Exception):
    pass


def _periods(now: datetime) -> list[dict[str, Any]]:
    timezone = ZoneInfo(get_settings().server_timezone)
    local_now = now.astimezone(timezone)
    week_start_date = local_now.date() - timedelta(days=local_now.weekday())
    month_start_date = local_now.date().replace(day=1)
    definitions: list[tuple[str, date, date]] = [
        (
            "WEEKLY",
            week_start_date,
            week_start_date + timedelta(days=7),
        ),
        (
            "MONTHLY",
            month_start_date,
            (
                month_start_date.replace(year=month_start_date.year + 1, month=1)
                if month_start_date.month == 12
                else month_start_date.replace(month=month_start_date.month + 1)
            ),
        ),
    ]
    result = []
    for season_type, start_date, end_date in definitions:
        start_local = datetime.combine(start_date, time.min, tzinfo=timezone)
        end_local = datetime.combine(end_date, time.min, tzinfo=timezone)
        if season_type == "WEEKLY":
            season_id = f"WEEKLY-{start_date:%Y%m%d}"
        else:
            season_id = f"MONTHLY-{start_date:%Y%m}"
        result.append(
            {
                "season_id": season_id,
                "season_type": season_type,
                "start_at_utc": start_local.astimezone(UTC),
                "end_at_utc": end_local.astimezone(UTC),
            }
        )
    return result


async def _ensure_current_seasons(
    session: AsyncSession, now: datetime
) -> list[dict[str, Any]]:
    # Expired periods are finalized asynchronously by the outbox worker.
    periods = _periods(now)
    for period in periods:
        await session.execute(
            text("""
                INSERT INTO seasons
                    (season_id, season_type, start_at_utc, end_at_utc,
                     status, settlement_status)
                VALUES
                    (:season_id, :season_type, :start_at_utc, :end_at_utc,
                     'ACTIVE', 'PENDING')
                ON CONFLICT (season_id) DO UPDATE
                SET status = CASE
                    WHEN seasons.status IN ('SCHEDULED','ACTIVE')
                    THEN 'ACTIVE'
                    ELSE seasons.status
                END
            """),
            period,
        )
    return periods


async def _refresh_leaderboard_snapshot(
    session: AsyncSession, season_id: str, board_type: str
) -> None:
    await session.execute(
        text("""
            WITH totals AS (
                SELECT player_id, SUM(delta)::bigint AS score
                FROM score_events
                WHERE period_id = :season_id AND board_type = :board_type
                GROUP BY player_id
            ),
            ranked AS (
                SELECT player_id, score,
                       DENSE_RANK() OVER (ORDER BY score DESC)::integer AS rank
                FROM totals
            )
            INSERT INTO leaderboard_snapshots
                (season_id, board_type, player_id, score, rank, snapshot_at_utc)
            SELECT :season_id, :board_type, player_id, score, rank, now()
            FROM ranked
            ON CONFLICT (season_id, board_type, player_id)
            DO UPDATE SET
                score = EXCLUDED.score,
                rank = EXCLUDED.rank,
                snapshot_at_utc = EXCLUDED.snapshot_at_utc
        """),
        {"season_id": season_id, "board_type": board_type},
    )


async def _write_score_event(
    session: AsyncSession,
    player_id: UUID,
    reason: str,
    source_event_id: str,
    run_id: UUID | None,
    idempotency_key: str,
) -> dict[str, Any]:
    config = (
        await session.execute(
            text("""
                SELECT board_type::text AS board_type, delta, config_status, is_enabled
                FROM score_rule_config
                WHERE reason = :reason
            """),
            {"reason": reason},
        )
    ).mappings().one_or_none()
    if (
        config is None
        or not config["is_enabled"]
        or config["config_status"] != "READY"
        or config["delta"] is None
    ):
        return {"written": False, "reason": "SCORE_TUNING_REQUIRED"}

    now = datetime.now(UTC)
    periods = await _ensure_current_seasons(session, now)
    written_periods = []
    for period in periods:
        inserted = (
            await session.execute(
                text("""
                    INSERT INTO score_events
                        (player_id, board_type, period_id, delta, reason,
                         source_event_id, run_id, idempotency_key, created_at_utc)
                    VALUES
                        (:player_id, :board_type, :period_id, :delta, :reason,
                         :source_event_id, :run_id, :idempotency_key, :now)
                    ON CONFLICT (board_type, period_id, idempotency_key)
                    DO NOTHING
                    RETURNING event_id
                """),
                {
                    "player_id": player_id,
                    "board_type": config["board_type"],
                    "period_id": period["season_id"],
                    "delta": config["delta"],
                    "reason": reason,
                    "source_event_id": source_event_id,
                    "run_id": run_id,
                    "idempotency_key": idempotency_key,
                    "now": now,
                },
            )
        ).scalar_one_or_none()
        if inserted is not None:
            await _refresh_leaderboard_snapshot(
                session, period["season_id"], config["board_type"]
            )
            written_periods.append(period["season_id"])
    return {
        "written": bool(written_periods),
        "period_ids": written_periods,
        "delta": config["delta"],
        "board_type": config["board_type"],
    }


async def _grant_rewards_for_trigger(
    session: AsyncSession,
    player_id: UUID,
    trigger_type: str,
    trigger_ref: str,
    source: str,
    source_id: str,
    is_repeat: bool = False,
) -> list[str]:
    rows = (
        await session.execute(
            text("""
                SELECT c.condition_id, c.condition_config, r.reward_id,
                       r.grant_mode::text AS grant_mode, r.is_paid
                FROM reward_conditions AS c
                JOIN rewards AS r ON r.reward_id = c.reward_id
                WHERE c.trigger_type = :trigger_type
                  AND c.is_enabled = true AND c.config_status = 'READY'
                  AND r.is_enabled = true AND r.is_paid = false
            """),
            {"trigger_type": trigger_type},
        )
    ).mappings().all()
    granted = []
    for row in rows:
        if trigger_type not in {"DISCOVERY", "COLLECTION", "SETTLEMENT"}:
            continue
        condition = row["condition_config"]
        reference_key = {
            "DISCOVERY": "discovery_id",
            "COLLECTION": "collection_id",
            "SETTLEMENT": "level_id",
        }.get(trigger_type)
        if reference_key and condition.get(reference_key) != trigger_ref:
            continue
        if is_repeat and not condition.get("repeatable", False):
            continue
        reward_status = (
            "PENDING_CLAIM" if row["grant_mode"] == "CLAIM" else "OWNED"
        )
        key = f"{source}:{source_id}:{row['reward_id']}"
        if len(key) > 200:
            key = key[:200]
        inserted = (
            await session.execute(
                text("""
                    INSERT INTO player_rewards
                        (player_id, reward_id, grant_mode, status, source,
                         source_id, idempotency_key)
                    VALUES
                        (:player_id, :reward_id, :grant_mode, :status, :source,
                         :source_id, :idempotency_key)
                    ON CONFLICT DO NOTHING
                    RETURNING player_reward_id
                """),
                {
                    "player_id": player_id,
                    "reward_id": row["reward_id"],
                    "grant_mode": row["grant_mode"],
                    "status": reward_status,
                    "source": source,
                    "source_id": source_id,
                    "idempotency_key": key,
                },
            )
        ).scalar_one_or_none()
        if inserted is not None:
            granted.append(row["reward_id"])
    return granted


async def _snapshot_progress(
    session: AsyncSession, player_id: UUID
) -> int:
    player = (
        await session.execute(
            text("""
                UPDATE players
                SET progress_version = progress_version + 1, updated_at = now()
                WHERE player_id = :player_id
                RETURNING progress_version, current_character_id
            """),
            {"player_id": player_id},
        )
    ).mappings().one()

    completed = (
        await session.execute(
            text("""
                SELECT DISTINCT level_id
                FROM settlements
                WHERE player_id = :player_id AND result_status = 'COMPLETED'
                ORDER BY level_id
            """),
            {"player_id": player_id},
        )
    ).scalars().all()
    discoveries = (
        await session.execute(
            text("""
                SELECT discovery_id FROM player_discoveries
                WHERE player_id = :player_id ORDER BY discovery_id
            """),
            {"player_id": player_id},
        )
    ).scalars().all()
    collections = (
        await session.execute(
            text("""
                SELECT collection_id FROM player_collections
                WHERE player_id = :player_id ORDER BY collection_id
            """),
            {"player_id": player_id},
        )
    ).scalars().all()
    rewards = (
        await session.execute(
            text("""
                SELECT reward_id, status::text AS status
                FROM player_rewards WHERE player_id = :player_id
                ORDER BY reward_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    routes = (
        await session.execute(
            text("""
                SELECT hidden_route_id FROM player_unlocked_hidden_routes
                WHERE player_id = :player_id ORDER BY hidden_route_id
            """),
            {"player_id": player_id},
        )
    ).scalars().all()
    scores = (
        await session.execute(
            text("""
                SELECT board_type::text AS board_type, period_id,
                       SUM(delta)::bigint AS score
                FROM score_events
                WHERE player_id = :player_id
                GROUP BY board_type, period_id
                ORDER BY board_type, period_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    permanent = {
        "discovery_ids": list(discoveries),
        "collection_ids": list(collections),
        "owned_reward_ids": [
            row["reward_id"] for row in rewards if row["status"] == "OWNED"
        ],
        "pending_reward_ids": [
            row["reward_id"]
            for row in rewards
            if row["status"] == "PENDING_CLAIM"
        ],
        "unlocked_hidden_routes": list(routes),
        "score_totals": [
            {
                "board_type": row["board_type"],
                "period_id": row["period_id"],
                "score": row["score"],
            }
            for row in scores
        ],
        "current_character_id": (
            str(player["current_character_id"])
            if player["current_character_id"] is not None
            else None
        ),
    }
    await session.execute(
        text("""
            INSERT INTO progress_snapshots
                (player_id, progress_version, completed_level_ids, permanent_progress)
            VALUES
                (:player_id, :progress_version,
                 CAST(:completed_level_ids AS jsonb),
                 CAST(:permanent_progress AS jsonb))
        """),
        {
            "player_id": player_id,
            "progress_version": player["progress_version"],
            "completed_level_ids": json.dumps(list(completed)),
            "permanent_progress": json.dumps(permanent),
        },
    )
    return player["progress_version"]


async def record_discovery(
    session: AsyncSession,
    player_id: UUID,
    discovery_id: str,
    run_id: UUID | None,
    level_id: str | None,
    location: dict[str, Any],
    related_rule: str | None = None,
    create_snapshot: bool = True,
) -> dict[str, Any]:
    catalog = (
        await session.execute(
            text("""
                SELECT discovery_type::text AS discovery_type, level_id,
                       related_rule, is_enabled, config_status, score_reason
                FROM discovery_catalog
                WHERE discovery_id = :discovery_id
            """),
            {"discovery_id": discovery_id},
        )
    ).mappings().one_or_none()
    if catalog is None or not catalog["is_enabled"] or catalog["config_status"] != "READY":
        return {"recorded": False, "discovery_id": discovery_id}

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
                "discovery_type": catalog["discovery_type"],
                "level_id": level_id or catalog["level_id"],
                "run_id": run_id,
                "location": json.dumps(location),
                "related_rule": related_rule or catalog["related_rule"],
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
            "recorded": True,
            "personal_first": False,
            "world_first": False,
            "new_collections": [],
        }

    now = datetime.now(UTC)
    world_first = (
        await session.execute(
            text("""
                INSERT INTO world_archive
                    (discovery_id, first_player_id, first_discovered_at,
                     location, related_rule)
                VALUES
                    (:discovery_id, :player_id, :now,
                     CAST(:location AS jsonb), :related_rule)
                ON CONFLICT (discovery_id) DO NOTHING
                RETURNING discovery_id
            """),
            {
                "discovery_id": discovery_id,
                "player_id": player_id,
                "now": now,
                "location": json.dumps(location),
                "related_rule": related_rule or catalog["related_rule"],
            },
        )
    ).scalar_one_or_none() is not None

    new_collections: list[str] = []
    collection_rows = (
        await session.execute(
            text("""
                SELECT collection_id, codex_category::text AS codex_category
                FROM collection_catalog
                WHERE source_discovery_id = :discovery_id AND is_enabled = true
            """),
            {"discovery_id": discovery_id},
        )
    ).mappings().all()
    for collection in collection_rows:
        collection_inserted = (
            await session.execute(
                text("""
                    INSERT INTO player_collections
                        (player_id, collection_id, codex_category, source, source_id)
                    VALUES
                        (:player_id, :collection_id, :codex_category,
                         'DISCOVERY', :source_id)
                    ON CONFLICT (player_id, collection_id) DO NOTHING
                    RETURNING collection_id
                """),
                {
                    "player_id": player_id,
                    "collection_id": collection["collection_id"],
                    "codex_category": collection["codex_category"],
                    "source_id": discovery_id,
                },
            )
        ).scalar_one_or_none()
        if collection_inserted is not None:
            new_collections.append(collection["collection_id"])
            await _write_score_event(
                session,
                player_id,
                "COLLECT_NEW",
                collection["collection_id"],
                run_id,
                f"collection:{player_id}:{collection['collection_id']}",
            )
            await _grant_rewards_for_trigger(
                session,
                player_id,
                "COLLECTION",
                collection["collection_id"],
                "DISCOVERY",
                discovery_id,
            )

    if catalog["score_reason"]:
        await _write_score_event(
            session,
            player_id,
            catalog["score_reason"],
            discovery_id,
            run_id,
            f"discovery:{player_id}:{discovery_id}",
        )
    granted = await _grant_rewards_for_trigger(
        session,
        player_id,
        "DISCOVERY",
        discovery_id,
        "DISCOVERY",
        discovery_id,
    )
    if create_snapshot:
        await _snapshot_progress(session, player_id)
    return {
        "recorded": True,
        "personal_first": True,
        "world_first": world_first,
        "new_collections": new_collections,
        "granted_rewards": granted,
    }


async def settle_level(
    session: AsyncSession,
    player_id: UUID,
    run_id: UUID,
    idempotency_key: str,
) -> dict[str, Any]:
    run = (
        await session.execute(
            text("""
                SELECT r.run_id, r.level_id, r.status::text AS run_status,
                       r.started_at, l.necessary_objectives, l.hard_time_limit,
                       l.time_limit_seconds, l.repeatable, l.repeat_reward_mode
                FROM level_runs AS r
                JOIN levels AS l ON l.level_id = r.level_id
                WHERE r.run_id = :run_id AND r.player_id = :player_id
                FOR UPDATE OF r
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise SettlementRunNotFound

    existing = (
        await session.execute(
            text("""
                SELECT result_id, level_id, result_status, completion_time_ms,
                       score_payload, created_at
                FROM settlements
                WHERE run_id = :run_id AND player_id = :player_id
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if existing is not None:
        await session.commit()
        return {
            "result_id": str(existing["result_id"]),
            "level_id": existing["level_id"],
            "result_status": existing["result_status"],
            "completion_time_ms": existing["completion_time_ms"],
            "score_payload": existing["score_payload"],
            "idempotent_replay": True,
        }

    stored_idempotency_key = hashlib.sha256(
        (str(player_id) + ":" + idempotency_key).encode("utf-8")
    ).hexdigest()
    conflicting_key = (
        await session.execute(
            text("""
                SELECT result_id FROM settlements
                WHERE idempotency_key = :idempotency_key
            """),
            {"idempotency_key": stored_idempotency_key},
        )
    ).scalar_one_or_none()
    if conflicting_key is not None:
        raise SettlementIdempotencyConflict
    if run["run_status"] != "RUNNING":
        raise SettlementStateConflict

    objectives = (
        await session.execute(
            text("""
                SELECT objective_id, mechanism_config_id, condition_type,
                       expected_state, expected_value, config, config_status
                FROM level_objectives
                WHERE level_id = :level_id AND is_required = true
                ORDER BY objective_id
            """),
            {"level_id": run["level_id"]},
        )
    ).mappings().all()
    if not objectives or any(
        objective["config_status"] != "READY" for objective in objectives
    ):
        raise SettlementConfigIncomplete

    states = (
        await session.execute(
            text("""
                SELECT mechanism_config_id, state
                FROM mechanism_states
                WHERE run_id = :run_id AND player_id = :player_id
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().all()
    state_by_mechanism = {
        row["mechanism_config_id"]: row["state"] for row in states
    }
    incomplete = []
    for objective in objectives:
        state = state_by_mechanism.get(objective["mechanism_config_id"], {})
        condition_type = objective["condition_type"]
        if condition_type == "STATE_EQUALS":
            completed = state.get("status") == objective["expected_state"]
        elif condition_type == "STATE_BOOLEAN":
            expected = json.loads(objective["expected_value"])
            state_key = objective["config"].get("state_key")
            completed = state.get(state_key) is expected
        elif condition_type == "COMBO_APPLIED":
            completed = state.get("combo_applied") == objective["expected_value"]
        else:
            completed = False
        if not completed:
            incomplete.append(objective["objective_id"])
    if incomplete:
        raise IncompleteObjectives(incomplete)

    now = datetime.now(UTC)
    completion_time_ms = max(
        0, int((now - run["started_at"]).total_seconds() * 1000)
    )
    if (
        run["hard_time_limit"]
        and run["time_limit_seconds"] is not None
        and completion_time_ms > run["time_limit_seconds"] * 1000
    ):
        failed_payload = {"failure_reason": "HARD_TIME_LIMIT"}
        failed_result = (
            await session.execute(
                text("""
                    INSERT INTO settlements
                        (run_id, player_id, level_id, result_status,
                         completion_time_ms, score_payload, idempotency_key)
                    VALUES
                        (:run_id, :player_id, :level_id, 'FAILED',
                         :completion_time_ms, CAST(:score_payload AS jsonb),
                         :idempotency_key)
                    RETURNING result_id
                """),
                {
                    "run_id": run_id,
                    "player_id": player_id,
                    "level_id": run["level_id"],
                    "completion_time_ms": completion_time_ms,
                    "score_payload": json.dumps(failed_payload),
                    "idempotency_key": stored_idempotency_key,
                },
            )
        ).scalar_one()
        await session.execute(
            text("""
                UPDATE level_runs
                SET status = 'FAILED', ended_at = :now,
                    completion_time_ms = :completion_time_ms, result_id = :result_id
                WHERE run_id = :run_id AND player_id = :player_id
            """),
            {
                "now": now,
                "completion_time_ms": completion_time_ms,
                "result_id": failed_result,
                "run_id": run_id,
                "player_id": player_id,
            },
        )
        await session.commit()
        return {
            "result_id": str(failed_result),
            "run_id": str(run_id),
            "level_id": run["level_id"],
            "result_status": "FAILED",
            "completion_time_ms": completion_time_ms,
            "score_payload": failed_payload,
            "idempotent_replay": False,
        }

    prior_completion = (
        await session.execute(
            text("""
                SELECT 1 FROM settlements
                WHERE player_id = :player_id AND level_id = :level_id
                  AND result_status = 'COMPLETED'
                LIMIT 1
            """),
            {"player_id": player_id, "level_id": run["level_id"]},
        )
    ).first()
    if prior_completion is not None and not run["repeatable"]:
        raise SettlementStateConflict

    result = (
        await session.execute(
            text("""
                INSERT INTO settlements
                    (run_id, player_id, level_id, result_status,
                     completion_time_ms, score_payload, idempotency_key)
                VALUES
                    (:run_id, :player_id, :level_id, 'COMPLETED',
                     :completion_time_ms, '{}'::jsonb, :idempotency_key)
                RETURNING result_id
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "level_id": run["level_id"],
                "completion_time_ms": completion_time_ms,
                "idempotency_key": stored_idempotency_key,
            },
        )
    ).scalar_one()
    await session.execute(
        text("""
            UPDATE level_runs
            SET status = 'COMPLETED', ended_at = :now,
                completion_time_ms = :completion_time_ms, result_id = :result_id
            WHERE run_id = :run_id AND player_id = :player_id
        """),
        {
            "now": now,
            "completion_time_ms": completion_time_ms,
            "result_id": result,
            "run_id": run_id,
            "player_id": player_id,
        },
    )

    puzzle_discovery = (
        "DISC-ENDING-01"
        if run["level_id"] == "LV-HIDDEN-01"
        else f"DISC-PUZZLE-ROOM{run['level_id'][-2:]}"
    )
    discovery_result = await record_discovery(
        session,
        player_id,
        puzzle_discovery,
        run_id,
        run["level_id"],
        {"level_id": run["level_id"], "run_id": str(run_id)},
        create_snapshot=False,
    )

    score_result = {"written": False, "reason": "REPEAT_REWARD_NONE"}
    if prior_completion is None or run["repeat_reward_mode"] == "FULL":
        score_result = await _write_score_event(
            session,
            player_id,
            "CLEAR_STAGE",
            str(result),
            run_id,
            f"settlement:{result}",
        )
    elif run["repeat_reward_mode"] == "REDUCED":
        score_result = {
            "written": False,
            "reason": "REPEAT_MULTIPLIER_TUNING_REQUIRED",
        }

    await _grant_rewards_for_trigger(
        session,
        player_id,
        "SETTLEMENT",
        run["level_id"],
        "SETTLEMENT",
        str(result),
        is_repeat=prior_completion is not None,
    )

    unlocked_route = await _try_unlock_hidden_route(
        session, player_id
    )
    await _snapshot_progress(session, player_id)
    score_payload = {
        "completed_objectives": [item["objective_id"] for item in objectives],
        "new_discovery": discovery_result,
        "clear_score": score_result,
        "unlocked_hidden_level_id": (
            unlocked_route["result_level_id"] if unlocked_route else None
        ),
    }
    await session.execute(
        text("""
            UPDATE settlements
            SET score_payload = CAST(:score_payload AS jsonb)
            WHERE result_id = :result_id
        """),
        {
            "score_payload": json.dumps(score_payload),
            "result_id": result,
        },
    )
    await session.commit()
    return {
        "result_id": str(result),
        "run_id": str(run_id),
        "level_id": run["level_id"],
        "result_status": "COMPLETED",
        "completion_time_ms": completion_time_ms,
        "score_payload": score_payload,
        "unlocked_hidden_level_id": (
            unlocked_route["result_level_id"] if unlocked_route else None
        ),
        "idempotent_replay": False,
    }


async def _try_unlock_hidden_route(
    session: AsyncSession,
    player_id: UUID,
) -> dict[str, Any] | None:
    routes = (
        await session.execute(
            text("""
                SELECT hidden_route_id, prerequisite_levels, trigger_level_id,
                       trigger_combo_sequence, trigger_mechanism_sequence,
                       result_level_id
                FROM hidden_routes
                WHERE is_enabled = true AND config_status = 'READY'
            """)
        )
    ).mappings().all()
    for route in routes:
        prerequisites = list(route["prerequisite_levels"])
        completed = (
            await session.execute(
                text("""
                    SELECT DISTINCT level_id
                    FROM settlements
                    WHERE player_id = :player_id AND result_status = 'COMPLETED'
                      AND level_id = ANY(CAST(:prerequisites AS varchar[]))
                """),
                {"player_id": player_id, "prerequisites": prerequisites},
            )
        ).scalars().all()
        if set(prerequisites) - set(completed):
            continue

        candidate_runs = (
            await session.execute(
                text("""
                    SELECT run_id
                    FROM settlements
                    WHERE player_id = :player_id
                      AND level_id = :trigger_level_id
                      AND result_status = 'COMPLETED'
                    ORDER BY created_at DESC
                """),
                {
                    "player_id": player_id,
                    "trigger_level_id": route["trigger_level_id"],
                },
            )
        ).scalars().all()
        expected_combos = list(route["trigger_combo_sequence"])
        expected_mechanisms = list(route["trigger_mechanism_sequence"])
        if len(expected_combos) != len(expected_mechanisms):
            continue

        matched_run_id = None
        for candidate_run_id in candidate_runs:
            combo_rows = (
                await session.execute(
                    text("""
                        SELECT result #>> '{combo,combo_id}' AS combo_id,
                               result #>> '{combo,mechanism_id}' AS mechanism_id
                        FROM rule_cast_events
                        WHERE run_id = :run_id AND player_id = :player_id
                          AND result #>> '{combo,combo_id}' IS NOT NULL
                        ORDER BY created_at ASC
                    """),
                    {"run_id": candidate_run_id, "player_id": player_id},
                )
            ).mappings().all()
            matched = 0
            for row in combo_rows:
                if (
                    row["combo_id"] == expected_combos[matched]
                    and row["mechanism_id"] == expected_mechanisms[matched]
                ):
                    matched += 1
                    if matched == len(expected_combos):
                        break
            if matched == len(expected_combos):
                matched_run_id = candidate_run_id
                break
        if matched_run_id is None:
            continue

        inserted = (
            await session.execute(
                text("""
                    INSERT INTO player_unlocked_hidden_routes
                        (player_id, hidden_route_id, source_run_id)
                    VALUES (:player_id, :route_id, :run_id)
                    ON CONFLICT (player_id, hidden_route_id) DO NOTHING
                    RETURNING hidden_route_id
                """),
                {
                    "player_id": player_id,
                    "route_id": route["hidden_route_id"],
                    "run_id": matched_run_id,
                },
            )
        ).scalar_one_or_none()
        await session.execute(
            text("""
                UPDATE mechanism_states
                SET state = state || CAST(:state AS jsonb), updated_at = now()
                WHERE run_id = :run_id AND player_id = :player_id
                  AND mechanism_config_id = 'M05-HIDDEN-GATE'
            """),
            {
                "run_id": matched_run_id,
                "player_id": player_id,
                "state": json.dumps({
                    "status": "TRIGGERED",
                    "visible": True,
                    "opened_by_route": route["hidden_route_id"],
                }),
            },
        )
        if inserted is not None:
            await record_discovery(
                session,
                player_id,
                "DISC-HIDDEN-ROUTE-01",
                matched_run_id,
                route["trigger_level_id"],
                {
                    "level_id": route["trigger_level_id"],
                    "run_id": str(matched_run_id),
                    "hidden_route_id": route["hidden_route_id"],
                },
                create_snapshot=False,
            )
        return {
            "hidden_route_id": route["hidden_route_id"],
            "result_level_id": route["result_level_id"],
            "newly_unlocked": inserted is not None,
        }
    return None


async def get_player_progress(
    session: AsyncSession, player_id: UUID
) -> dict[str, Any]:
    player = (
        await session.execute(
            text("""
                SELECT progress_version, current_character_id
                FROM players WHERE player_id = :player_id
            """),
            {"player_id": player_id},
        )
    ).mappings().one()
    snapshot = (
        await session.execute(
            text("""
                SELECT progress_version, completed_level_ids, permanent_progress,
                       created_at
                FROM progress_snapshots
                WHERE player_id = :player_id
                ORDER BY progress_version DESC LIMIT 1
            """),
            {"player_id": player_id},
        )
    ).mappings().one_or_none()
    if snapshot is None:
        return {
            "progress_version": player["progress_version"],
            "current_character_id": player["current_character_id"],
            "completed_level_ids": [],
            "permanent_progress": {},
        }
    return {
        "progress_version": snapshot["progress_version"],
        "current_character_id": player["current_character_id"],
        "completed_level_ids": snapshot["completed_level_ids"],
        "permanent_progress": snapshot["permanent_progress"],
        "snapshot_at": snapshot["created_at"].isoformat(),
    }


async def list_player_discoveries(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT d.discovery_id, d.discovery_type::text AS discovery_type,
                       d.display_name, d.level_id, d.related_rule,
                       p.first_discovered_at, p.trigger_count
                FROM player_discoveries AS p
                JOIN discovery_catalog AS d ON d.discovery_id = p.discovery_id
                WHERE p.player_id = :player_id
                ORDER BY p.first_discovered_at DESC, d.discovery_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def list_player_collections(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT c.collection_id, c.codex_category::text AS codex_category,
                       c.display_name, c.description, c.asset_id, c.sort_order,
                       p.source::text AS source, p.source_id, p.obtained_at
                FROM player_collections AS p
                JOIN collection_catalog AS c ON c.collection_id = p.collection_id
                WHERE p.player_id = :player_id
                ORDER BY c.codex_category, c.sort_order, c.collection_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def list_world_archive(
    session: AsyncSession, limit: int = 50
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT a.discovery_id, d.display_name,
                       a.first_player_id, a.first_discovered_at,
                       a.location, a.related_rule
                FROM world_archive AS a
                JOIN discovery_catalog AS d ON d.discovery_id = a.discovery_id
                ORDER BY a.first_discovered_at ASC
                LIMIT :limit
            """),
            {"limit": limit},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def list_player_rewards(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT p.player_reward_id, p.reward_id, r.reward_type::text AS reward_type,
                       r.reward_name, r.payload, p.grant_mode::text AS grant_mode,
                       p.status::text AS status, p.source, p.source_id,
                       p.granted_at, p.claimed_at
                FROM player_rewards AS p
                JOIN rewards AS r ON r.reward_id = p.reward_id
                WHERE p.player_id = :player_id
                ORDER BY p.granted_at DESC, p.player_reward_id
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def claim_reward(
    session: AsyncSession, player_id: UUID, player_reward_id: UUID
) -> dict[str, Any]:
    reward = (
        await session.execute(
            text("""
                SELECT player_reward_id, reward_id, grant_mode::text AS grant_mode,
                       status::text AS status, claimed_at
                FROM player_rewards
                WHERE player_reward_id = :player_reward_id
                  AND player_id = :player_id
                FOR UPDATE
            """),
            {"player_reward_id": player_reward_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if reward is None:
        raise RewardNotFound
    if reward["status"] == "OWNED":
        await session.commit()
        return {
            "player_reward_id": str(player_reward_id),
            "reward_id": reward["reward_id"],
            "status": "OWNED",
            "already_claimed": True,
        }
    if reward["grant_mode"] != "CLAIM":
        raise RewardNotClaimable
    await session.execute(
        text("""
            UPDATE player_rewards
            SET status = 'OWNED', claimed_at = now()
            WHERE player_reward_id = :player_reward_id AND player_id = :player_id
        """),
        {"player_reward_id": player_reward_id, "player_id": player_id},
    )
    await _snapshot_progress(session, player_id)
    await session.commit()
    return {
        "player_reward_id": str(player_reward_id),
        "reward_id": reward["reward_id"],
        "status": "OWNED",
        "already_claimed": False,
    }


async def get_leaderboard(
    session: AsyncSession,
    player_id: UUID,
    board_type: str,
    period_type: str,
    scope: str = "TOP",
    limit: int = 20,
    season_id: str | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    if season_id is None:
        period = next(
            item for item in _periods(now) if item["season_type"] == period_type
        )
        resolved_season_id = period["season_id"]
        fallback_start_at = period["start_at_utc"]
        fallback_end_at = period["end_at_utc"]
    else:
        resolved_season_id = season_id
        fallback_start_at = None
        fallback_end_at = None

    season = (
        await session.execute(
            text("""
                SELECT season_id, season_type::text AS season_type,
                       start_at_utc, end_at_utc, status::text AS status
                FROM seasons WHERE season_id = :season_id
            """),
            {"season_id": resolved_season_id},
        )
    ).mappings().one_or_none()
    if season_id is not None:
        # An explicit season is answered from its archived snapshot, or from the current
        # period when the row has not been materialised yet. Anything else is rejected:
        # silently falling back to the current period would mislabel another season's ranks.
        if season is not None:
            period_type = season["season_type"]
        else:
            current_period = next(
                (item for item in _periods(now) if item["season_id"] == season_id), None
            )
            if current_period is None:
                raise LeaderboardSeasonNotFound(season_id)
            period_type = current_period["season_type"]
            fallback_start_at = current_period["start_at_utc"]
            fallback_end_at = current_period["end_at_utc"]

    my_rank = (
        await session.execute(
            text("""
                SELECT rank, score
                FROM leaderboard_snapshots
                WHERE season_id = :season_id AND board_type = :board_type
                  AND player_id = :player_id
            """),
            {
                "season_id": resolved_season_id,
                "board_type": board_type,
                "player_id": player_id,
            },
        )
    ).mappings().one_or_none()
    if scope == "SELF":
        if my_rank is None:
            rows = []
        else:
            rows = (
                await session.execute(
                    text("""
                        SELECT player_id, score, rank, snapshot_at_utc
                        FROM leaderboard_snapshots
                        WHERE season_id = :season_id AND board_type = :board_type
                          AND player_id = :player_id
                    """),
                    {
                        "season_id": resolved_season_id,
                        "board_type": board_type,
                        "player_id": player_id,
                    },
                )
            ).mappings().all()
    elif scope == "AROUND" and my_rank is not None:
        rows = (
            await session.execute(
                text("""
                    SELECT player_id, score, rank, snapshot_at_utc
                    FROM leaderboard_snapshots
                    WHERE season_id = :season_id AND board_type = :board_type
                      AND rank BETWEEN :rank_start AND :rank_end
                    ORDER BY rank, player_id
                """),
                {
                    "season_id": resolved_season_id,
                    "board_type": board_type,
                    "rank_start": max(1, my_rank["rank"] - 3),
                    "rank_end": my_rank["rank"] + 3,
                },
            )
        ).mappings().all()
    else:
        rows = (
            await session.execute(
                text("""
                    SELECT player_id, score, rank, snapshot_at_utc
                    FROM leaderboard_snapshots
                    WHERE season_id = :season_id AND board_type = :board_type
                    ORDER BY rank, player_id
                    LIMIT :limit
                """),
                {
                    "season_id": resolved_season_id,
                    "board_type": board_type,
                    "limit": min(max(limit, 1), 50),
                },
            )
        ).mappings().all()
    return {
        "season_id": resolved_season_id,
        "period_type": period_type,
        "start_at_utc": (
            season["start_at_utc"].isoformat()
            if season is not None
            else fallback_start_at.isoformat()
        ),
        "end_at_utc": (
            season["end_at_utc"].isoformat()
            if season is not None
            else fallback_end_at.isoformat()
        ),
        "board_type": board_type,
        "scope": scope,
        "entries": [
            {
                "player_id": str(row["player_id"]),
                "score": row["score"],
                "rank": row["rank"],
                "snapshot_at": row["snapshot_at_utc"].isoformat(),
                "is_self": row["player_id"] == player_id,
            }
            for row in rows
        ],
        "my_rank": (
            {"rank": my_rank["rank"], "score": my_rank["score"]}
            if my_rank is not None
            else None
        ),
        "is_snapshot": True,
    }


async def recompute_leaderboard(
    session: AsyncSession,
    season_id: str,
    board_type: str,
    apply: bool,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Rebuild one board of one period from the score_events ledger.

    GDD 13.6 requires recomputation to treat the ledger as the only authority, to
    leave historical events untouched, and to record the before/after difference
    for review. Snapshots are derived data, so they may be rewritten; score_events
    never are.
    """
    existing_season = (
        await session.execute(
            text("SELECT season_id FROM seasons WHERE season_id = :season_id"),
            {"season_id": season_id},
        )
    ).scalar_one_or_none()
    if existing_season is None:
        raise LeaderboardSeasonNotFound(season_id)

    ledger_rows = (
        await session.execute(
            text("""
                SELECT player_id, SUM(delta)::bigint AS score
                FROM score_events
                WHERE period_id = :season_id AND board_type = :board_type
                GROUP BY player_id
            """),
            {"season_id": season_id, "board_type": board_type},
        )
    ).mappings().all()
    snapshot_rows = (
        await session.execute(
            text("""
                SELECT player_id, score, rank
                FROM leaderboard_snapshots
                WHERE season_id = :season_id AND board_type = :board_type
            """),
            {"season_id": season_id, "board_type": board_type},
        )
    ).mappings().all()

    ledger_totals = {row["player_id"]: row["score"] for row in ledger_rows}
    snapshot_scores = {row["player_id"]: row["score"] for row in snapshot_rows}

    differences = []
    for player_id, score in ledger_totals.items():
        snapshot_score = snapshot_scores.get(player_id)
        if snapshot_score != score:
            differences.append(
                {
                    "player_id": str(player_id),
                    "snapshot_score": snapshot_score,
                    "recomputed_score": score,
                }
            )
    for player_id, snapshot_score in snapshot_scores.items():
        if player_id not in ledger_totals:
            differences.append(
                {
                    "player_id": str(player_id),
                    "snapshot_score": snapshot_score,
                    "recomputed_score": 0,
                }
            )
    differences.sort(key=lambda item: item["player_id"])

    result: dict[str, Any] = {
        "season_id": season_id,
        "board_type": board_type,
        "players_in_ledger": len(ledger_totals),
        "players_in_snapshot": len(snapshot_scores),
        "difference_count": len(differences),
        "differences": differences[:100],
        "truncated": len(differences) > 100,
        "applied": False,
    }
    if not apply or not differences:
        return result

    # Snapshots are derived, so drop and rebuild them rather than patching rows.
    await session.execute(
        text("""
            DELETE FROM leaderboard_snapshots
            WHERE season_id = :season_id AND board_type = :board_type
        """),
        {"season_id": season_id, "board_type": board_type},
    )
    await _refresh_leaderboard_snapshot(session, season_id, board_type)
    await session.execute(
        text("""
            INSERT INTO actions_log (action_type, payload, request_id)
            VALUES ('LEADERBOARD_RECOMPUTE', CAST(:payload AS jsonb), :request_id)
        """),
        {"payload": json.dumps(result), "request_id": request_id},
    )
    result["applied"] = True
    return result
