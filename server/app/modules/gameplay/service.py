import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

_CATALOG_PATH = Path(__file__).with_name("levels.v1.json")
_RULES = {"RULE_ECHO", "RULE_GAZE", "RULE_REVERSE"}
_COMBOS = {
    frozenset(("RULE_ECHO", "RULE_GAZE")): ("COMBO-001", ("RULE_ECHO", "RULE_GAZE")),
    frozenset(("RULE_ECHO", "RULE_REVERSE")): ("COMBO-002", None),
    frozenset(("RULE_GAZE", "RULE_REVERSE")): ("COMBO-003", ("RULE_GAZE", "RULE_REVERSE")),
}


class LevelRunNotFound(Exception):
    pass


class MechanismNotFound(Exception):
    pass


class InvalidLawAction(Exception):
    pass


class LawCooldown(Exception):
    pass


class LawIdempotencyConflict(Exception):
    pass


def _catalog() -> dict[str, Any]:
    return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))


def _level_config(level_id: str) -> dict[str, Any]:
    for level in _catalog()["levels"]:
        if level["level_id"] == level_id:
            return level
    raise ValueError(f"Level {level_id} is missing from the authoritative content catalog")


def _request_hash(rule_id: str, mechanism_id: str, action: str) -> str:
    raw = json.dumps(
        {"rule_id": rule_id, "mechanism_id": mechanism_id, "action": action},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _initial_state(mechanism: dict[str, Any]) -> dict[str, Any]:
    initial = mechanism["initial_state"]
    return {
        "state": initial,
        "base_state": initial,
        "active_rules": [],
        "revealed": initial not in {"HIDDEN", "INVISIBLE", "SEALED"},
        "gaze_active": False,
        "reversed": False,
        "combo_completed": False,
        "combo_id": None,
        "version": 1,
        "config": mechanism.get("config", {}),
    }


async def initialize_mechanisms(
    session: AsyncSession, run_id: UUID, player_id: UUID, level_id: str
) -> None:
    level = _level_config(level_id)
    for mechanism in level["mechanisms"]:
        await session.execute(
            text("""
                INSERT INTO mechanism_states
                    (run_id, player_id, mechanism_config_id, mechanism_type, state)
                VALUES
                    (:run_id, :player_id, :mechanism_id, :mechanism_type, CAST(:state AS jsonb))
                ON CONFLICT (run_id, mechanism_config_id) DO NOTHING
            """),
            {
                "run_id": run_id,
                "player_id": player_id,
                "mechanism_id": mechanism["mechanism_id"],
                "mechanism_type": mechanism["mechanism_type"],
                "state": json.dumps(_initial_state(mechanism), separators=(",", ":")),
            },
        )


def _apply_single_rule(
    mechanism_type: str, state: dict[str, Any], rule_id: str, action: str
) -> None:
    if action == "RELEASE":
        if rule_id == "RULE_GAZE":
            state["gaze_active"] = False
            state["active_rules"] = [r for r in state["active_rules"] if r != rule_id]
            if not state["combo_completed"] and state["state"] == "VISIBLE_HELD":
                state["state"] = state["base_state"]
        elif rule_id == "RULE_REVERSE":
            state["reversed"] = False
            state["active_rules"] = [r for r in state["active_rules"] if r != rule_id]
            if not state["combo_completed"] and state["state"] in {"REVERSED", "MOVING_REVERSE"}:
                state["state"] = state["base_state"]
        else:
            raise InvalidLawAction("Echo is an instantaneous pulse and cannot be released")
        return

    if rule_id == "RULE_ECHO":
        if mechanism_type not in {
            "HIDEABLE",
            "LIGHT_REVEAL",
            "ENERGY_NODE",
            "HIDDEN_GATE",
            "PLATFORM_BRIDGE",
        }:
            raise InvalidLawAction("Echo cannot affect this mechanism type")
        state["revealed"] = True
        if mechanism_type == "HIDEABLE":
            state["state"] = "REVEALED"
        elif mechanism_type == "LIGHT_REVEAL":
            state["state"] = "ACTIVE"
        elif mechanism_type == "HIDDEN_GATE" and state["base_state"] == "SEALED":
            state["state"] = "REVEALED"
        elif mechanism_type == "PLATFORM_BRIDGE" and state["base_state"] == "INVISIBLE":
            state["state"] = "REVEALED"
    elif rule_id == "RULE_GAZE":
        if mechanism_type not in {"PLATFORM_BRIDGE", "MOVING_OBJECT", "ENERGY_NODE", "HIDEABLE"}:
            raise InvalidLawAction("Gaze cannot affect this mechanism type")
        state["gaze_active"] = True
        if rule_id not in state["active_rules"]:
            state["active_rules"].append(rule_id)
        if state["state"] in {"INVISIBLE", "UNSTABLE", "HIDDEN"}:
            state["state"] = "VISIBLE_HELD"
    elif rule_id == "RULE_REVERSE":
        if mechanism_type not in {"MOVING_OBJECT", "ENERGY_NODE", "PLATFORM_BRIDGE"}:
            raise InvalidLawAction("Reverse cannot affect this mechanism type")
        state["reversed"] = True
        if rule_id not in state["active_rules"]:
            state["active_rules"].append(rule_id)
        state["state"] = "REVERSED" if mechanism_type == "ENERGY_NODE" else "MOVING_REVERSE"



def _combo_for_pair(first: str, second: str, elapsed_ms: int) -> str | None:
    entry = _COMBOS.get(frozenset((first, second)))
    if entry is None:
        return None
    combo_id, valid_order = entry
    if valid_order is not None and (first, second) != valid_order:
        return None
    if elapsed_ms > get_settings().law_combo_window_ms:
        return None
    return combo_id


async def apply_law_action(
    session: AsyncSession,
    player_id: UUID,
    run_id: UUID,
    rule_id: str,
    mechanism_id: str,
    action: str,
    idempotency_key: str,
) -> dict[str, Any]:
    if rule_id not in _RULES or action not in {"APPLY", "RELEASE"}:
        raise InvalidLawAction("Unsupported law or action")
    request_hash = _request_hash(rule_id, mechanism_id, action)

    run = (
        await session.execute(
            text("""
                SELECT run_id, level_id, status::text AS run_status
                FROM level_runs
                WHERE run_id = :run_id AND player_id = :player_id
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise LevelRunNotFound
    if run["run_status"] != "RUNNING":
        raise InvalidLawAction("Law actions require a RUNNING personal level")

    prior = (
        await session.execute(
            text("""
                SELECT request_hash, result
                FROM law_action_events
                WHERE run_id = :run_id AND idempotency_key = :idempotency_key
            """),
            {"run_id": run_id, "idempotency_key": idempotency_key},
        )
    ).mappings().one_or_none()
    if prior is not None:
        if prior["request_hash"] != request_hash:
            raise LawIdempotencyConflict
        await session.rollback()
        return {**prior["result"], "idempotent_replay": True}

    mechanism = (
        await session.execute(
            text("""
                SELECT mechanism_type, state
                FROM mechanism_states
                WHERE run_id = :run_id AND player_id = :player_id
                  AND mechanism_config_id = :mechanism_id
                FOR UPDATE
            """),
            {"run_id": run_id, "player_id": player_id, "mechanism_id": mechanism_id},
        )
    ).mappings().one_or_none()
    if mechanism is None:
        raise MechanismNotFound

    settings = get_settings()
    if settings.law_cooldown_ms > 0 and action == "APPLY":
        last = (
            await session.execute(
                text("""
                    SELECT created_at FROM law_action_events
                    WHERE run_id = :run_id AND mechanism_config_id = :mechanism_id
                      AND rule_id = :rule_id AND action = 'APPLY'
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"run_id": run_id, "mechanism_id": mechanism_id, "rule_id": rule_id},
            )
        ).scalar_one_or_none()
        if last is not None:
            remaining = settings.law_cooldown_ms - int(
                (datetime.now(timezone.utc) - last).total_seconds() * 1000
            )
            if remaining > 0:
                raise LawCooldown(f"Law is cooling down for {remaining} ms")

    state = dict(mechanism["state"])
    _apply_single_rule(mechanism["mechanism_type"], state, rule_id, action)

    combo_id = None
    if action == "APPLY":
        previous = (
            await session.execute(
                text("""
                    SELECT rule_id, created_at
                    FROM law_action_events
                    WHERE run_id = :run_id AND mechanism_config_id = :mechanism_id
                      AND action = 'APPLY'
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"run_id": run_id, "mechanism_id": mechanism_id},
            )
        ).mappings().one_or_none()
        if previous is not None and previous["rule_id"] != rule_id:
            elapsed = int(
                (datetime.now(timezone.utc) - previous["created_at"]).total_seconds() * 1000
            )
            combo_id = _combo_for_pair(previous["rule_id"], rule_id, elapsed)

    level = _level_config(run["level_id"])
    configured_combos = set(level.get("required_combos", []))
    if combo_id not in configured_combos:
        combo_id = None
    if combo_id:
        state["combo_completed"] = True
        state["combo_id"] = combo_id
        state["active_rules"] = sorted(set(state["active_rules"]) | {rule_id})
        if combo_id == "COMBO-001":
            state["state"] = "OPEN"
            state["gaze_active"] = True
            state["revealed"] = True
        elif combo_id == "COMBO-002":
            state["state"] = "REVERSED"
            state["reversed"] = True
            for sibling in level["mechanisms"]:
                if sibling["config"].get("open_on_combo") == combo_id:
                    sibling_row = (
                        await session.execute(
                            text("""
                                SELECT state FROM mechanism_states
                                WHERE run_id = :run_id AND mechanism_config_id = :mechanism_id
                                FOR UPDATE
                            """),
                            {"run_id": run_id, "mechanism_id": sibling["mechanism_id"]},
                        )
                    ).scalar_one_or_none()
                    if sibling_row is not None:
                        sibling_state = dict(sibling_row)
                        sibling_state["state"] = "OPEN"
                        sibling_state["combo_completed"] = True
                        sibling_state["combo_id"] = combo_id
                        sibling_state["version"] += 1
                        await session.execute(
                            text("""
                                UPDATE mechanism_states SET state = CAST(:state AS jsonb), updated_at = now()
                                WHERE run_id = :run_id AND mechanism_config_id = :mechanism_id
                            """),
                            {"state": json.dumps(sibling_state), "run_id": run_id, "mechanism_id": sibling["mechanism_id"]},
                        )
        elif combo_id == "COMBO-003":
            state["state"] = "ENDPOINT_LOCKED"
            state["reversed"] = True
            state["gaze_active"] = True

    state["version"] += 1
    await session.execute(
        text("""
            UPDATE mechanism_states
            SET state = CAST(:state AS jsonb), updated_at = now()
            WHERE run_id = :run_id AND mechanism_config_id = :mechanism_id
        """),
        {
            "state": json.dumps(state, separators=(",", ":")),
            "run_id": run_id,
            "mechanism_id": mechanism_id,
        },
    )

    result = {
        "run_id": str(run_id),
        "mechanism_id": mechanism_id,
        "rule_id": rule_id,
        "action": action,
        "state": state,
        "combo_id": combo_id,
        "idempotent_replay": False,
    }
    await session.execute(
        text("""
            INSERT INTO law_action_events
                (run_id, player_id, idempotency_key, request_hash, rule_id,
                 mechanism_config_id, action, combo_id, result)
            VALUES
                (:run_id, :player_id, :idempotency_key, :request_hash, :rule_id,
                 :mechanism_id, :action, :combo_id, CAST(:result AS jsonb))
        """),
        {
            "run_id": run_id,
            "player_id": player_id,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "rule_id": rule_id,
            "mechanism_id": mechanism_id,
            "action": action,
            "combo_id": combo_id,
            "result": json.dumps(result, separators=(",", ":")),
        },
    )
    await session.commit()
    return result


async def get_run_mechanisms(
    session: AsyncSession, player_id: UUID, run_id: UUID
) -> dict[str, Any]:
    run = (
        await session.execute(
            text("""
                SELECT level_id, status::text AS run_status
                FROM level_runs WHERE run_id = :run_id AND player_id = :player_id
            """),
            {"run_id": run_id, "player_id": player_id},
        )
    ).mappings().one_or_none()
    if run is None:
        raise LevelRunNotFound
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
    return {
        "run_id": str(run_id),
        "level_id": run["level_id"],
        "status": run["run_status"],
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
