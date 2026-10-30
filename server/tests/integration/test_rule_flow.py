# ruff: noqa: I001
from pathlib import Path

import asyncio
import json
import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.main import app
from app.modules.auth.provider import get_wechat_code_provider


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL and apply Alembic migrations for PostgreSQL integration tests",
)


class FakeWeChatProvider:
    async def exchange(self, code: str) -> str:
        return f"rule-test-openid-{code}"


def _db_update(statement: str, parameters: dict | None = None) -> None:
    async def execute() -> None:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(text(statement), parameters or {})
        finally:
            await engine.dispose()

    asyncio.run(execute())


def _login_and_enter_map(client: TestClient) -> dict:
    login = client.post(
        "/api/v1/auth/login",
        json={"wx_code": str(uuid4()), "request_id": "rule-test-login"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    entered = client.post("/api/v1/map/enter", headers=headers)
    assert entered.status_code == 200
    return {"headers": headers, "token": token}


def _enter_level(client: TestClient, headers: dict, level_id: str, entrance_id: str) -> str:
    entered = client.post(
        "/api/v1/level/enter",
        headers={**headers, "Idempotency-Key": f"rule-enter-{uuid4()}"},
        json={"level_id": level_id, "entrance_id": entrance_id},
    )
    assert entered.status_code == 200, entered.text
    run_id = entered.json()["data"]["run_id"]
    started = client.post(
        "/api/v1/level/start",
        headers=headers,
        json={"run_id": run_id},
    )
    assert started.status_code == 200, started.text
    return run_id


def _set_rule_tuning(ready: bool) -> None:
    if ready:
        _db_update("""
            UPDATE rule_catalog
            SET cooldown_ms = 5000, radius = 2.0, duration_ms = 1000,
                lease_timeout_ms = 5000, config_status = 'READY'
        """)
        _db_update("""
            UPDATE combo_catalog
            SET time_window_ms = 10000, config_status = 'READY'
        """)
    else:
        _db_update("""
            UPDATE rule_catalog
            SET cooldown_ms = NULL, radius = NULL, duration_ms = NULL,
                lease_timeout_ms = NULL, config_status = 'TUNING_REQUIRED'
        """)
        _db_update("""
            UPDATE combo_catalog
            SET time_window_ms = NULL, config_status = 'TUNING_REQUIRED'
        """)


def test_authoritative_laws_combos_cooldowns_and_personal_isolation() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            first = _login_and_enter_map(client)
            second = _login_and_enter_map(client)
            third = _login_and_enter_map(client)

            first_run = _enter_level(
                client, first["headers"], "LV-ROOM-02", "ENT-ROOM-02"
            )
            laws = client.get("/api/v1/level/rules", headers=first["headers"])
            assert laws.status_code == 200
            assert {item["rule_id"] for item in laws.json()["data"]["rules"]} == {
                "RULE_ECHO",
                "RULE_GAZE",
                "RULE_REVERSE",
            }
            assert all(item["is_unlocked"] for item in laws.json()["data"]["rules"])

            not_tuned = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **first["headers"],
                    "Idempotency-Key": "rule-not-tuned-0001",
                },
                json={
                    "run_id": first_run,
                    "rule_id": "RULE_ECHO",
                    "target_id": "M02-BRIDGE-01",
                    "target_point": {"x": 0, "y": 0},
                },
            )
            assert not_tuned.status_code == 503

            _set_rule_tuning(True)
            echo_headers = {
                **first["headers"],
                "Idempotency-Key": "rule-echo-room2-0001",
            }
            echo_payload = {
                "run_id": first_run,
                "rule_id": "RULE_ECHO",
                "target_id": "M02-BRIDGE-01",
                "target_point": {"x": 6, "y": 4},
            }
            echo = client.post(
                "/api/v1/level/rule/cast",
                headers=echo_headers,
                json=echo_payload,
            )
            assert echo.status_code == 200, echo.text
            assert echo.json()["data"]["effects"][0]["mechanism_id"] == "M02-BRIDGE-01"

            replay = client.post(
                "/api/v1/level/rule/cast",
                headers=echo_headers,
                json=echo_payload,
            )
            assert replay.status_code == 200
            assert replay.json()["data"]["idempotent_replay"] is True

            gaze = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **first["headers"],
                    "Idempotency-Key": "rule-gaze-room2-0001",
                },
                json={
                    "run_id": first_run,
                    "rule_id": "RULE_GAZE",
                    "target_id": "M02-BRIDGE-01",
                },
            )
            assert gaze.status_code == 200, gaze.text
            assert gaze.json()["data"]["combo"]["combo_id"] == "COMBO-001"

            cooling = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **first["headers"],
                    "Idempotency-Key": "rule-echo-room2-0002",
                },
                json=echo_payload,
            )
            assert cooling.status_code == 409
            assert cooling.json()["detail"]["code"] == "RULE_COOLDOWN"

            maintained = client.post(
                "/api/v1/level/rule/maintain",
                headers=first["headers"],
                json={"run_id": first_run, "target_id": "M02-BRIDGE-01"},
            )
            assert maintained.status_code == 200

            stopped = client.post(
                "/api/v1/level/rule/stop",
                headers=first["headers"],
                json={"run_id": first_run},
            )
            assert stopped.status_code == 200

            first_state = client.get(
                f"/api/v1/level/state/{first_run}", headers=first["headers"]
            )
            bridge = first_state.json()["data"]["mechanisms"][0]["state"]
            assert bridge["status"] == "TRIGGERED"
            assert bridge["combo_applied"] == "COMBO-001"
            assert bridge["visible"] is True

            second_run = _enter_level(
                client, second["headers"], "LV-ROOM-02", "ENT-ROOM-02"
            )
            second_state = client.get(
                f"/api/v1/level/state/{second_run}", headers=second["headers"]
            )
            assert second_state.status_code == 200
            second_mechanisms = second_state.json()["data"]["mechanisms"]
            assert len(second_mechanisms) == 1
            second_bridge = second_mechanisms[0]["state"]
            assert second_bridge["status"] == "INACTIVE"
            assert second_bridge["visible"] is False
            assert "combo_applied" not in second_bridge

            wrong_order_gaze = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **second["headers"],
                    "Idempotency-Key": "rule-gaze-wrong-order-0001",
                },
                json={
                    "run_id": second_run,
                    "rule_id": "RULE_GAZE",
                    "target_id": "M02-BRIDGE-01",
                },
            )
            assert wrong_order_gaze.status_code == 200
            wrong_order_echo = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **second["headers"],
                    "Idempotency-Key": "rule-echo-wrong-order-0001",
                },
                json={
                    "run_id": second_run,
                    "rule_id": "RULE_ECHO",
                    "target_id": "M02-BRIDGE-01",
                    "target_point": {"x": 6, "y": 4},
                },
            )
            assert wrong_order_echo.status_code == 200
            assert wrong_order_echo.json()["data"]["combo"] is None
            wrong_order_state = client.get(
                f"/api/v1/level/state/{second_run}", headers=second["headers"]
            )
            assert (
                wrong_order_state.json()["data"]["mechanisms"][0]["state"]["status"]
                == "ACTIVE"
            )

            third_run = _enter_level(
                client, third["headers"], "LV-ROOM-03", "ENT-ROOM-03"
            )
            reverse = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **third["headers"],
                    "Idempotency-Key": "rule-reverse-room3-0001",
                },
                json={
                    "run_id": third_run,
                    "rule_id": "RULE_REVERSE",
                    "target_id": "M03-ENERGY-01",
                },
            )
            assert reverse.status_code == 200, reverse.text
            echo_after_reverse = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **third["headers"],
                    "Idempotency-Key": "rule-echo-room3-0001",
                },
                json={
                    "run_id": third_run,
                    "rule_id": "RULE_ECHO",
                    "target_id": "M03-ENERGY-01",
                    "target_point": {"x": 4, "y": 4},
                },
            )
            assert echo_after_reverse.status_code == 200
            assert (
                echo_after_reverse.json()["data"]["combo"]["combo_id"]
                == "COMBO-002"
            )
            reversed_state = client.get(
                f"/api/v1/level/state/{third_run}", headers=third["headers"]
            )
            energy = next(
                item["state"]
                for item in reversed_state.json()["data"]["mechanisms"]
                if item["mechanism_id"] == "M03-ENERGY-01"
            )
            assert energy["direction"] == -1
            assert energy["reverse_active"] is True

            time.sleep(1.2)
            expired_state = client.get(
                f"/api/v1/level/state/{third_run}", headers=third["headers"]
            )
            energy_after = next(
                item["state"]
                for item in expired_state.json()["data"]["mechanisms"]
                if item["mechanism_id"] == "M03-ENERGY-01"
            )
            assert energy_after["direction"] == 1
            assert energy_after["reverse_active"] is False
    finally:
        _set_rule_tuning(False)
        app.dependency_overrides.clear()


def test_room_five_supports_all_three_preset_combos() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            player = _login_and_enter_map(client)
            _set_rule_tuning(True)
            _db_update("UPDATE rule_catalog SET cooldown_ms = 1")
            run_id = _enter_level(
                client, player["headers"], "LV-ROOM-05", "ENT-ROOM-05"
            )
            initial_state = client.get(
                f"/api/v1/level/state/{run_id}", headers=player["headers"]
            )
            assert initial_state.status_code == 200
            bridge = next(
                item for item in initial_state.json()["data"]["mechanisms"]
                if item["mechanism_id"] == "M05-BRIDGE-01"
            )
            assert (bridge["position_x"], bridge["position_y"]) == (3.0, 4.0)

            def cast(rule_id: str, target_id: str, key: str, point=None):
                payload = {
                    "run_id": run_id,
                    "rule_id": rule_id,
                    "target_id": target_id,
                }
                if point is not None:
                    payload["target_point"] = point
                return client.post(
                    "/api/v1/level/rule/cast",
                    headers={
                        **player["headers"],
                        "Idempotency-Key": key,
                    },
                    json=payload,
                )

            echo_bridge = cast(
                "RULE_ECHO", "M05-BRIDGE-01", "room5-echo-bridge-0001",
                {"x": 3, "y": 4},
            )
            assert echo_bridge.status_code == 200, echo_bridge.text
            gaze_bridge = cast(
                "RULE_GAZE", "M05-BRIDGE-01", "room5-gaze-bridge-0001"
            )
            assert gaze_bridge.status_code == 200, gaze_bridge.text
            assert gaze_bridge.json()["data"]["combo"]["combo_id"] == "COMBO-001"

            # Gaze is a sustained effect; release its current target before
            # moving to the next mechanism in the same personal run.
            stopped_gaze = client.post(
                "/api/v1/level/rule/stop",
                headers=player["headers"],
                json={"run_id": run_id},
            )
            assert stopped_gaze.status_code == 200, stopped_gaze.text

            time.sleep(0.01)
            echo_energy = cast(
                "RULE_ECHO", "M05-ENERGY-01", "room5-echo-energy-0001",
                {"x": 6, "y": 4},
            )
            assert echo_energy.status_code == 200, echo_energy.text
            reverse_energy = cast(
                "RULE_REVERSE", "M05-ENERGY-01", "room5-reverse-energy-0001"
            )
            assert reverse_energy.status_code == 200, reverse_energy.text
            assert reverse_energy.json()["data"]["combo"]["combo_id"] == "COMBO-002"

            # Reverse is time-limited (1s in this test fixture). Let the
            # authoritative effect expire before targeting another mechanism.
            time.sleep(1.1)
            gaze_platform = cast(
                "RULE_GAZE", "M05-REVERSE-01", "room5-gaze-platform-0001"
            )
            assert gaze_platform.status_code == 200, gaze_platform.text
            reverse_platform = cast(
                "RULE_REVERSE", "M05-REVERSE-01", "room5-reverse-platform-0001"
            )
            assert reverse_platform.status_code == 200, reverse_platform.text
            assert reverse_platform.json()["data"]["combo"]["combo_id"] == "COMBO-003"

            # The settlement objectives must point at these same ROOM-05
            # mechanisms; otherwise combo state can never satisfy the clear.
            settled = client.post(
                "/api/v1/level/settle",
                headers={
                    **player["headers"],
                    "Idempotency-Key": "room5-settle-after-three-combos",
                },
                json={"run_id": run_id},
            )
            assert settled.status_code == 200, settled.text
            assert settled.json()["data"]["result_status"] == "COMPLETED"
    finally:
        _set_rule_tuning(False)
        app.dependency_overrides.clear()



def test_mechanism_catalog_and_references_match_canonical_gdd_ids() -> None:
    async def fetch_contract() -> dict:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as connection:
                catalog = await connection.execute(
                    text(
                        """
                        SELECT level_id, mechanism_config_id, mechanism_type, is_enabled,
                               position_x, position_y, config
                        FROM level_mechanism_catalog
                        """
                    )
                )
                objectives_without_mechanisms = await connection.scalar(
                    text(
                        """
                        SELECT count(*)
                        FROM level_objectives AS objective
                        LEFT JOIN level_mechanism_catalog AS mechanism
                          ON mechanism.level_id = objective.level_id
                         AND mechanism.mechanism_config_id = objective.mechanism_config_id
                        WHERE mechanism.mechanism_config_id IS NULL
                        """
                    )
                )
                route = await connection.scalar(
                    text(
                        """
                        SELECT trigger_mechanism_sequence
                        FROM hidden_routes
                        WHERE hidden_route_id = 'HIDDEN-ROUTE-01'
                        """
                    )
                )
                room5_objectives = await connection.execute(
                    text(
                        """
                        SELECT objective_id, mechanism_config_id
                        FROM level_objectives
                        WHERE level_id = 'LV-ROOM-05'
                        ORDER BY objective_id
                        """
                    )
                )
                combo_targets = await connection.execute(
                    text(
                        """
                        SELECT target_mechanism_id
                        FROM combo_catalog
                        ORDER BY combo_id
                        """
                    )
                )
                hidden_discovery = await connection.scalar(
                    text(
                        """
                        SELECT trigger_condition->>'mechanism_id'
                        FROM discovery_catalog
                        WHERE discovery_id = 'DISC-HIDDEN-OBJ-ROOM01'
                        """
                    )
                )
            return {
                "catalog": [dict(row._mapping) for row in catalog],
                "objectives_without_mechanisms": objectives_without_mechanisms,
                "room5_objectives": [dict(row._mapping) for row in room5_objectives],
                "route": route,
                "combo_targets": [row[0] for row in combo_targets],
                "hidden_discovery": hidden_discovery,
            }
        finally:
            await engine.dispose()

    contract = asyncio.run(fetch_contract())
    ids = {
        (row["level_id"], row["mechanism_config_id"])
        for row in contract["catalog"]
    }
    assert ("LV-ROOM-01", "M01-HIDEABLE-01") in ids
    assert ("LV-ROOM-01", "M01-LIGHT-01") in ids
    assert ("LV-ROOM-01", "M01-EXIT-01") in ids
    assert ("LV-ROOM-03", "M03-DOOR-01") in ids
    assert ("LV-HIDDEN-01", "H01-GATE") in ids
    assert ("LV-HIDDEN-01", "H01-END") in ids
    assert contract["objectives_without_mechanisms"] == 0
    assert contract["route"] == [
        "M05-BRIDGE-01",
        "M05-ENERGY-01",
        "M05-REVERSE-01",
    ]
    assert {
        row["mechanism_config_id"] for row in contract["room5_objectives"]
    } == {
        "M05-BRIDGE-01",
        "M05-ENERGY-01",
        "M05-REVERSE-01",
    }
    enabled_room5_ids = {
        row["mechanism_config_id"]
        for row in contract["catalog"]
        if row["level_id"] == "LV-ROOM-05" and row["is_enabled"]
    }
    assert {
        "M05-BRIDGE-01",
        "M05-ENERGY-01",
        "M05-REVERSE-01",
    } <= enabled_room5_ids
    assert not {
        "M02-BRIDGE-01",
        "M03-ENERGY-01",
        "M04-PLATFORM-01",
    } & enabled_room5_ids
    prototype_ids = {
        ("LV-ROOM-02", "M02-BRIDGE-01"),
        ("LV-ROOM-03", "M03-ENERGY-01"),
        ("LV-ROOM-03", "M03-DOOR-01"),
        ("LV-ROOM-04", "M04-PLATFORM-01"),
        ("LV-ROOM-04", "M04-PLATFORM-02"),
        ("LV-ROOM-05", "M05-BRIDGE-01"),
        ("LV-ROOM-05", "M05-ENERGY-01"),
        ("LV-ROOM-05", "M05-REVERSE-01"),
        ("LV-ROOM-05", "M05-HIDDEN-GATE"),
        ("LV-HIDDEN-01", "H01-GATE"),
        ("LV-HIDDEN-01", "H01-END"),
    }
    configured_prototypes = {
        (row["level_id"], row["mechanism_config_id"])
        for row in contract["catalog"]
        if row["is_enabled"]
        and row["position_x"] is not None
        and row["position_y"] is not None
        and row["config"].get("prototype_only") is True
    }
    assert prototype_ids <= configured_prototypes
    level_config_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "engineering"
        / "levels"
        / "levels.v1.json"
    )
    source_config = json.loads(level_config_path.read_text(encoding="utf-8"))
    catalog_by_key = {
        (row["level_id"], row["mechanism_config_id"]): row
        for row in contract["catalog"]
    }
    for level in source_config["levels"]:
        for mechanism in level["mechanisms"]:
            row = catalog_by_key[(level["level_id"], mechanism["mechanism_id"])]
            assert row["position_x"] == mechanism["position"]["x"]
            assert row["position_y"] == mechanism["position"]["y"]
            assert row["config"].get("prototype_only") is True
    assert contract["combo_targets"] == [
        "M02-BRIDGE-01",
        "M03-ENERGY-01",
        "M04-PLATFORM-01",
    ]
    assert contract["hidden_discovery"] == "M01-HIDEABLE-01"
