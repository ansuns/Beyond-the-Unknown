import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.progression.service import mark_objective_complete, record_discovery


class RuleRunNotFound(Exception):
    pass


class RuleNotUnlocked(Exception):
    pass


class RuleNotFound(Exception):
    pass


class RuleConfigurationIncomplete(Exception):
    pass


class RuleCoolingDown(Exception):
    def __init__(self, remaining_ms: int):
        self.remaining_ms = remaining_ms


class RuleTargetInvalid(Exception):
    pass


class RuleIdempotencyConflict(Exception):
    pass


class RuleStateConflict(Exception):
    pass


def _hash_request(
    rule_id: str, target_id: str | None, target_point: dict[str, float] | None
) -> str:
    payload = json.dumps(
        {"rule_id": rule_id, "target_id": target_id, "target_point": target_point},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def list_player_rules(
    session: AsyncSession, player_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text("""
                SELECT r.rule_id, r.display_name, r.duration_type, r.priority,
                       r.scope_type, r.cooldown_ms, r.radius, r.duration_ms,
                       r.lease_timeout_ms, r.allowed_target_types, r.config_status,
                       (u.rule_id IS NOT NULL) AS is_unlocked
                FROM rule_catalog AS r
                LEFT JOIN player_unlocked_rules AS u
                  ON u.rule_id = r.rule_id AND u.player_id = :player_id
                WHERE r.is_enabled = true
                ORDER BY r.priority DESC
            """),
            {"player_id": player_id},
        )
    ).mappings().all()
    return [dict(row) for row in rows]


async def _get_run(
    session: AsyncSession, player_id: UUID, run_id: UUID
) -> Any:
    run = (
        await session.execute(
            text("""
                SELECT r.run_id, r.level_id, r.status::text AS run_status
                FROM level_runs AS r
                WHERE r.run_id = :run_id AND r.player_id = :player_id
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise RuleRunNotFound
    if run["run_status"] != "RUNNING":
        raise RuleStateConflict
    return run


async def _load_mechanism_state(
    session: AsyncSession,
    run_id: UUID,
    player_id: UUID,
    mechanism: Any,
) -> dict[str, Any]:
    await session.execute(
        text("""
            INSERT INTO mechanism_states
                (run_id, player_id, mechanism_config_id, mechanism_type, state)
            VALUES (:run_id, :player_id, :mechanism_id, :mechanism_type, CAST(:state AS jsonb))
            ON CONFLICT (run_id, mechanism_config_id) DO NOTHING
        """),
        {
            "run_id": run_id,
            "player_id": player_id,
            "mechanism_id": mechanism["mechanism_config_id"],
            "mechanism_type": mechanism["mechanism_type"],
            "state": json.dumps({
                "status": mechanism["initial_state"],
                "direction": mechanism["config"].get("initial_direction", 1),
                "visible": mechanism["config"].get("visible_by_default", False),
            }),
        },
    )
    row = (
        await session.execute(
            text("""
                SELECT state
                FROM mechanism_states
                WHERE run_id = :run_id AND player_id = :player_id
                  AND mechanism_config_id = :mechanism_id
                FOR UPDATE
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "mechanism_id": mechanism["mechanism_config_id"],
            },
        )
    ).mappings().one()
    return dict(row["state"])


async def _save_mechanism_state(
    session: AsyncSession,
    run_id: UUID,
    player_id: UUID,
    mechanism_id: str,
    state: dict[str, Any],
) -> None:
    await session.execute(
        text("""
            UPDATE mechanism_states
            SET state = CAST(:state AS jsonb), updated_at = now()
            WHERE run_id = :run_id AND player_id = :player_id
              AND mechanism_config_id = :mechanism_id
        """),
        {
            "state": json.dumps(state),
            "run_id": run_id,
            "player_id": player_id,
            "mechanism_id": mechanism_id,
        },
    )


async def _expire_rule_effects(
    session: AsyncSession,
    run_id: UUID,
    player_id: UUID,
    level_id: str,
    now: datetime,
) -> None:
    rows = (
        await session.execute(
            text("""
                SELECT s.rule_id, s.active_target_id, s.expires_at,
                       s.last_maintained_at, r.duration_type, r.lease_timeout_ms
                FROM player_rule_states AS s
                JOIN rule_catalog AS r ON r.rule_id = s.rule_id
                WHERE s.run_id = :run_id AND s.player_id = :player_id
                  AND s.active_target_id IS NOT NULL
                FOR UPDATE OF s
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().all()
    for row in rows:
        expired = (
            row["duration_type"] == "TIMED"
            and row["expires_at"] is not None
            and row["expires_at"] <= now
        )
        if (
            row["duration_type"] == "WHILE_CASTING"
            and row["lease_timeout_ms"] is not None
            and row["last_maintained_at"] is not None
        ):
            expired = expired or (
                row["last_maintained_at"]
                + timedelta(milliseconds=row["lease_timeout_ms"])
                <= now
            )
        if not expired:
            continue
        mechanism = (
            await session.execute(
                text("""
                    SELECT mechanism_config_id, mechanism_type, initial_state,
                           target_state, trigger_rule, config
                    FROM level_mechanism_catalog
                    WHERE level_id = :level_id AND mechanism_config_id = :target_id
                """),
                {"level_id": level_id, "target_id": row["active_target_id"]},
            )
        ).mappings().one_or_none()
        if mechanism is not None:
            state = await _load_mechanism_state(
                session, run_id, player_id, mechanism
            )
            if row["rule_id"] == "RULE_REVERSE":
                state["reverse_active"] = False
                state["direction"] = int(
                    state.get("original_direction", state.get("direction", 1))
                )
                state.pop("reverse_until", None)
            elif row["rule_id"] == "RULE_GAZE":
                state["gaze_active"] = False
                state["visible_by_gaze"] = False
                if not state.get("visible_by_echo"):
                    state["visible"] = mechanism["config"].get(
                        "visible_by_default", False
                    )
                    if state.get("status") != "LOCKED":
                        state["status"] = mechanism["initial_state"]
            await _save_mechanism_state(
                session, run_id, player_id, row["active_target_id"], state
            )
        await session.execute(
            text("""
                UPDATE player_rule_states
                SET active_target_id = NULL, active_effect = '{}'::jsonb,
                    expires_at = NULL, last_maintained_at = NULL, updated_at = :now
                WHERE run_id = :run_id AND player_id = :player_id
                  AND rule_id = :rule_id
            """),
            {
                "now": now,
                "run_id": run_id,
                "player_id": player_id,
                "rule_id": row["rule_id"],
            },
        )


async def cast_rule(
    session: AsyncSession,
    player_id: UUID,
    run_id: UUID,
    rule_id: str,
    target_id: str | None,
    target_point: dict[str, float] | None,
    idempotency_key: str,
) -> dict[str, Any]:
    request_hash = _hash_request(rule_id, target_id, target_point)
    run = await _get_run(session, player_id, run_id)
    now = datetime.now(UTC)
    await _expire_rule_effects(
        session, run_id, player_id, run["level_id"], now
    )

    prior = (
        await session.execute(
            text("""
                SELECT request_hash, result
                FROM rule_cast_events
                WHERE run_id = :run_id AND player_id = :player_id
                  AND idempotency_key = :idempotency_key
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "idempotency_key": idempotency_key,
            },
        )
    ).mappings().one_or_none()
    if prior is not None:
        if prior["request_hash"] != request_hash:
            raise RuleIdempotencyConflict
        result = dict(prior["result"])
        result["idempotent_replay"] = True
        await session.commit()
        return result

    unlocked = (
        await session.execute(
            text("""
                SELECT 1 FROM player_unlocked_rules
                WHERE player_id = :player_id AND rule_id = :rule_id
            """),
            {"player_id": player_id, "rule_id": rule_id},
        )
    ).first()
    if unlocked is None:
        raise RuleNotUnlocked

    rule = (
        await session.execute(
            text("""
                SELECT rule_id, duration_type, scope_type, cooldown_ms, radius,
                       duration_ms, lease_timeout_ms, allowed_target_types,
                       config_status
                FROM rule_catalog
                WHERE rule_id = :rule_id AND is_enabled = true
            """),
            {"rule_id": rule_id},
        )
    ).mappings().one_or_none()
    if rule is None:
        raise RuleNotFound
    if (
        rule["config_status"] != "READY"
        or rule["cooldown_ms"] is None
        or rule["radius"] is None
        or (
            rule["duration_type"] == "TIMED"
            and rule["duration_ms"] is None
        )
        or (
            rule["duration_type"] == "WHILE_CASTING"
            and rule["lease_timeout_ms"] is None
        )
    ):
        raise RuleConfigurationIncomplete

    await session.execute(
        text("""
            INSERT INTO player_rule_states (run_id, player_id, rule_id)
            VALUES (:run_id, :player_id, :rule_id)
            ON CONFLICT (run_id, player_id, rule_id) DO NOTHING
        """),
        {"run_id": run_id, "player_id": player_id, "rule_id": rule_id},
    )
    rule_state = (
        await session.execute(
            text("""
                SELECT cooldown_until, active_target_id, active_effect,
                       expires_at, last_maintained_at
                FROM player_rule_states
                WHERE run_id = :run_id AND player_id = :player_id
                  AND rule_id = :rule_id
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id, "rule_id": rule_id},
        )
    ).mappings().one()
    if rule_state["cooldown_until"] and rule_state["cooldown_until"] > now:
        remaining = int((rule_state["cooldown_until"] - now).total_seconds() * 1000)
        raise RuleCoolingDown(max(remaining, 1))

    allowed_types = set(rule["allowed_target_types"])
    if rule_id == "RULE_ECHO":
        if target_point is None:
            raise RuleTargetInvalid
        x, y = target_point["x"], target_point["y"]
        if not math.isfinite(x) or not math.isfinite(y):
            raise RuleTargetInvalid
        candidates = (
            await session.execute(
                text("""
                    SELECT level_id, mechanism_config_id, mechanism_type, target_type,
                           initial_state, target_state, trigger_rule,
                           position_x, position_y, config
                    FROM level_mechanism_catalog
                    WHERE level_id = :level_id AND is_enabled = true
                      AND position_x IS NOT NULL AND position_y IS NOT NULL
                      AND power(position_x - :x, 2) + power(position_y - :y, 2)
                          <= power(:radius, 2)
                    ORDER BY mechanism_config_id
                """),
                {
                    "level_id": run["level_id"],
                    "x": x,
                    "y": y,
                    "radius": rule["radius"],
                },
            )
        ).mappings().all()
        mechanisms = [
            item for item in candidates if item["target_type"] in allowed_types
        ]
        if target_id is not None and not any(
            item["mechanism_config_id"] == target_id for item in mechanisms
        ):
            raise RuleTargetInvalid
    else:
        if not target_id or target_point is not None:
            raise RuleTargetInvalid
        target = (
            await session.execute(
                text("""
                    SELECT level_id, mechanism_config_id, mechanism_type, target_type,
                           initial_state, target_state, trigger_rule,
                           position_x, position_y, config
                    FROM level_mechanism_catalog
                    WHERE level_id = :level_id
                      AND mechanism_config_id = :target_id AND is_enabled = true
                """),
                {"level_id": run["level_id"], "target_id": target_id},
            )
        ).mappings().one_or_none()
        if target is None or target["target_type"] not in allowed_types:
            raise RuleTargetInvalid
        if target["position_x"] is None or target["position_y"] is None:
            raise RuleConfigurationIncomplete
        mechanisms = [target]

    effects: list[dict[str, Any]] = []
    for mechanism in mechanisms:
        state = await _load_mechanism_state(session, run_id, player_id, mechanism)
        if state.get("status") == "LOCKED":
            continue
        if state.get("status") == "INACTIVE":
            state["status"] = "ACTIVE"

        if rule_id == "RULE_ECHO":
            state["visible"] = True
            state["visible_by_echo"] = True
            state["last_rule"] = rule_id
        elif rule_id == "RULE_GAZE":
            state["visible"] = True
            state["visible_by_gaze"] = True
            state["gaze_active"] = True
            state["last_rule"] = rule_id
        elif rule_id == "RULE_REVERSE":
            if not state.get("reverse_active"):
                state["original_direction"] = int(state.get("direction", 1))
                state["direction"] = -state["original_direction"]
            state["reverse_active"] = True
            state["reverse_until"] = (
                now + timedelta(milliseconds=rule["duration_ms"])
            ).isoformat()
            state["last_rule"] = rule_id

        await _save_mechanism_state(
            session,
            run_id,
            player_id,
            mechanism["mechanism_config_id"],
            state,
        )
        effects.append(
            {
                "mechanism_id": mechanism["mechanism_config_id"],
                "state": state,
            }
        )

    combo_result = await _match_combo(
        session,
        run_id,
        player_id,
        run["level_id"],
        rule_id,
        target_id,
        now,
    )

    if effects:
        await record_discovery(
            session, player_id, run_id, f"DISC-{rule_id.replace('_', '-')}"
        )
        if rule_id == "RULE_ECHO" and any(
            item["mechanism_type"] == "HIDEABLE" for item in mechanisms
        ):
            await record_discovery(
                session, player_id, run_id, "DISC-HIDDEN-OBJ-ROOM01-01"
            )
            await mark_objective_complete(
                session,
                player_id,
                run_id,
                "HIDDEN_TARGET_REVEALED",
                f"rule:{run_id}:{idempotency_key}",
            )
    if combo_result is not None:
        combo_id = combo_result["combo_id"]
        await record_discovery(
            session, player_id, run_id, f"DISC-{combo_id}"
        )
        combo_objectives = {
            ("LV-ROOM-02", "COMBO-001"): "BRIDGE_OPEN",
            ("LV-ROOM-03", "COMBO-002"): "ENERGY_DOOR_OPEN",
            ("LV-ROOM-04", "COMBO-003"): "MOVING_PLATFORM_LOCKED",
            ("LV-ROOM-05", "COMBO-001"): "ROOM05_TARGET_A",
            ("LV-ROOM-05", "COMBO-002"): "ROOM05_TARGET_B",
            ("LV-ROOM-05", "COMBO-003"): "ROOM05_TARGET_C",
        }
        objective_id = combo_objectives.get((run["level_id"], combo_id))
        if objective_id is not None:
            await mark_objective_complete(
                session,
                player_id,
                run_id,
                objective_id,
                f"combo:{run_id}:{combo_id}:{target_id}",
            )
        puzzle_discoveries = {
            "COMBO-001": "DISC-PUZZLE-ROOM02-BRIDGE",
            "COMBO-002": "DISC-PUZZLE-ROOM03-ENERGY",
            "COMBO-003": "DISC-PUZZLE-ROOM04-PLATFORM",
        }
        puzzle_discovery = puzzle_discoveries.get(combo_id)
        if puzzle_discovery is not None:
            await record_discovery(
                session, player_id, run_id, puzzle_discovery
            )

    cooldown_until = now + timedelta(milliseconds=rule["cooldown_ms"])
    active_target = (
        target_id if rule_id in {"RULE_GAZE", "RULE_REVERSE"} else None
    )
    active_effect = (
        {"target_id": target_id, "effect": rule_id}
        if active_target is not None
        else {}
    )
    expires_at = (
        now + timedelta(milliseconds=rule["duration_ms"])
        if rule["duration_type"] == "TIMED"
        else None
    )
    await session.execute(
        text("""
            UPDATE player_rule_states
            SET cooldown_until = :cooldown_until,
                active_target_id = :active_target_id,
                active_effect = CAST(:active_effect AS jsonb),
                expires_at = :expires_at,
                last_maintained_at = CASE
                    WHEN :rule_id = 'RULE_GAZE' THEN :now ELSE last_maintained_at END,
                updated_at = :now
            WHERE run_id = :run_id AND player_id = :player_id AND rule_id = :rule_id
        """),
        {
            "cooldown_until": cooldown_until,
            "active_target_id": active_target,
            "active_effect": json.dumps(active_effect),
            "expires_at": expires_at,
            "rule_id": rule_id,
            "now": now,
            "run_id": run_id,
            "player_id": player_id,
        },
    )

    result = {
        "run_id": str(run_id),
        "rule_id": rule_id,
        "target_id": target_id,
        "effects": effects,
        "combo": combo_result,
        "cooldown_until": cooldown_until.isoformat(),
        "idempotent_replay": False,
    }
    await session.execute(
        text("""
            INSERT INTO rule_cast_events
                (run_id, player_id, rule_id, target_id, target_point,
                 idempotency_key, request_hash, result)
            VALUES (:run_id, :player_id, :rule_id, :target_id,
                    CAST(:target_point AS jsonb), :idempotency_key, :request_hash,
                    CAST(:result AS jsonb))
        """),
        {
            "run_id": run_id,
            "player_id": player_id,
            "rule_id": rule_id,
            "target_id": target_id,
            "target_point": json.dumps(target_point) if target_point is not None else None,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "result": json.dumps(result),
        },
    )
    await session.commit()
    return result


async def _match_combo(
    session: AsyncSession,
    run_id: UUID,
    player_id: UUID,
    level_id: str,
    current_rule_id: str,
    target_id: str | None,
    now: datetime,
) -> dict[str, Any] | None:
    if target_id is None:
        return None
    previous = (
        await session.execute(
            text("""
                SELECT rule_id, created_at
                FROM rule_cast_events
                WHERE run_id = :run_id AND player_id = :player_id
                  AND target_id = :target_id
                  AND rule_id <> :current_rule_id
                ORDER BY created_at DESC
                LIMIT 1
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "target_id": target_id,
                "current_rule_id": current_rule_id,
            },
        )
    ).mappings().one_or_none()
    if previous is None:
        return None

    combos = (
        await session.execute(
            text("""
                SELECT combo_id, rule_ids, order_sensitive, valid_order,
                       time_window_ms, result_effect, target_mechanism_id
                FROM combo_catalog
                WHERE is_hidden = false AND config_status = 'READY'
                  AND time_window_ms IS NOT NULL
            """)
        )
    ).mappings().all()
    for combo in combos:
        if set(combo["rule_ids"]) != {previous["rule_id"], current_rule_id}:
            continue
        if now - previous["created_at"] > timedelta(milliseconds=combo["time_window_ms"]):
            continue
        if combo["order_sensitive"]:
            valid = list(combo["valid_order"] or [])
            if valid != [previous["rule_id"], current_rule_id]:
                continue
        mechanism = (
            await session.execute(
                text("""
                    SELECT mechanism_config_id, mechanism_type, initial_state,
                           target_state, trigger_rule, config
                    FROM level_mechanism_catalog
                    WHERE level_id = :level_id
                      AND mechanism_config_id = :mechanism_id AND is_enabled = true
                """),
                {"level_id": level_id, "mechanism_id": target_id},
            )
        ).mappings().one_or_none()
        expected_types = {
            "MECH_BRIDGE": "PLATFORM_BRIDGE",
            "MECH_ENERGY_GATE": "ENERGY_NODE",
            "MECH_MOVING_PLATFORM": "MOVING_OBJECT",
        }
        if (
            mechanism is None
            or mechanism["mechanism_type"] != expected_types.get(
                combo["target_mechanism_id"]
            )
            or "COMBO_EFFECT" not in mechanism["trigger_rule"]
        ):
            continue
        state = await _load_mechanism_state(session, run_id, player_id, mechanism)
        if state.get("status") == "LOCKED":
            continue
        if state.get("status") in {"TRIGGERED", "LOCKED"}:
            return {
                "combo_id": combo["combo_id"],
                "mechanism_id": target_id,
                "status": state["status"],
                "already_applied": True,
            }
        transitions = list(state.get("transitions", []))
        if state.get("status") == "INACTIVE":
            transitions.append({"from": "INACTIVE", "to": "ACTIVE"})
            state["status"] = "ACTIVE"
        transitions.append({"from": "ACTIVE", "to": mechanism["target_state"]})
        state["status"] = mechanism["target_state"]
        state["combo_applied"] = combo["combo_id"]
        state["result_effect"] = combo["result_effect"]
        state["transitions"] = transitions
        if combo["result_effect"] == "REVEAL_AND_MAINTAIN_BRIDGE":
            state["visible"] = True
            state["visible_by_echo"] = True
            state["gaze_active"] = True
        elif combo["result_effect"] == "REVEAL_AND_REVERSE_ENERGY":
            state["visible"] = True
            state["visible_by_echo"] = True
            state["reverse_active"] = True
        elif combo["result_effect"] == "MAINTAIN_AND_REVERSE_PLATFORM":
            state["visible"] = True
            state["visible_by_gaze"] = True
            state["gaze_active"] = True
            state["reverse_active"] = True
        await _save_mechanism_state(
            session, run_id, player_id, target_id, state
        )
        return {
            "combo_id": combo["combo_id"],
            "mechanism_id": target_id,
            "status": state["status"],
        }
    return None


async def stop_gaze(
    session: AsyncSession, player_id: UUID, run_id: UUID
) -> dict[str, Any]:
    run = await _get_run(session, player_id, run_id)
    await _expire_rule_effects(
        session, run_id, player_id, run["level_id"], datetime.now(UTC)
    )
    state_row = (
        await session.execute(
            text("""
                SELECT active_target_id
                FROM player_rule_states
                WHERE run_id = :run_id AND player_id = :player_id
                  AND rule_id = 'RULE_GAZE'
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if state_row is None or state_row["active_target_id"] is None:
        await session.commit()
        return {"run_id": str(run_id), "stopped": False}
    target_id = state_row["active_target_id"]
    mechanism_row = (
        await session.execute(
            text("""
                SELECT mechanism_config_id, mechanism_type, initial_state,
                       target_state, trigger_rule, config
                FROM level_mechanism_catalog
                WHERE level_id = :level_id AND mechanism_config_id = :target_id
            """),
            {"level_id": run["level_id"], "target_id": target_id},
        )
    ).mappings().one_or_none()
    if mechanism_row is not None:
        state = await _load_mechanism_state(
            session, run_id, player_id, mechanism_row
        )
        state["gaze_active"] = False
        state["visible_by_gaze"] = False
        if not state.get("visible_by_echo"):
            state["visible"] = mechanism_row["config"].get(
                "visible_by_default", False
            )
            if state.get("status") != "LOCKED":
                state["status"] = mechanism_row["initial_state"]
        await _save_mechanism_state(
            session, run_id, player_id, target_id, state
        )
    await session.execute(
        text("""
            UPDATE player_rule_states
            SET active_target_id = NULL, active_effect = '{}'::jsonb,
                expires_at = NULL, last_maintained_at = NULL, updated_at = now()
            WHERE run_id = :run_id AND player_id = :player_id
              AND rule_id = 'RULE_GAZE'
        """),
        {"run_id": run_id, "player_id": player_id},
    )
    await session.commit()
    return {"run_id": str(run_id), "stopped": True, "target_id": target_id}



async def maintain_gaze(
    session: AsyncSession,
    player_id: UUID,
    run_id: UUID,
    target_id: str,
) -> dict[str, Any]:
    run = await _get_run(session, player_id, run_id)
    now = datetime.now(UTC)
    await _expire_rule_effects(
        session, run_id, player_id, run["level_id"], now
    )
    state = (
        await session.execute(
            text("""
                SELECT active_target_id
                FROM player_rule_states
                WHERE run_id = :run_id AND player_id = :player_id
                  AND rule_id = 'RULE_GAZE'
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if state is None or state["active_target_id"] != target_id:
        raise RuleStateConflict
    await session.execute(
        text("""
            UPDATE player_rule_states
            SET last_maintained_at = :now, updated_at = :now
            WHERE run_id = :run_id AND player_id = :player_id
              AND rule_id = 'RULE_GAZE'
        """),
        {"now": now, "run_id": run_id, "player_id": player_id},
    )
    await session.commit()
    return {"run_id": str(run_id), "target_id": target_id, "maintained_at": now.isoformat()}


async def get_level_state(
    session: AsyncSession, player_id: UUID, run_id: UUID
) -> dict[str, Any]:
    run = await _get_run(session, player_id, run_id)
    await _expire_rule_effects(
        session, run_id, player_id, run["level_id"], datetime.now(UTC)
    )
    rows = (
        await session.execute(
            text("""
                SELECT mechanism_config_id, mechanism_type, state, updated_at
                FROM mechanism_states
                WHERE run_id = :run_id AND player_id = :player_id
                ORDER BY mechanism_config_id
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().all()
    await session.commit()
    return {
        "run_id": str(run_id),
        "level_id": run["level_id"],
        "mechanisms": [
            {
                "mechanism_id": row["mechanism_config_id"],
                "mechanism_type": row["mechanism_type"],
                "state": row["state"],
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in rows
        ],
    }
