# ruff: noqa: I001

import asyncio
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
            SET cooldown_ms = 5000, radius = 2.0, duration_ms = 120,
                lease_timeout_ms = 5000, config_status = 'READY'
        """)
        _db_update("""
            UPDATE combo_catalog
            SET time_window_ms = 10000, config_status = 'READY'
        """)
        _db_update("""
            UPDATE level_mechanism_catalog
            SET position_x = 0, position_y = 0
            WHERE level_id = 'LV-ROOM-02' AND mechanism_config_id = 'MECH_BRIDGE'
        """)
        _db_update("""
            UPDATE level_mechanism_catalog
            SET position_x = 1, position_y = 1
            WHERE level_id = 'LV-ROOM-03' AND mechanism_config_id = 'MECH_ENERGY_GATE'
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
        _db_update("""
            UPDATE level_mechanism_catalog
            SET position_x = NULL, position_y = NULL
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
                    "target_id": "MECH_BRIDGE",
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
                "target_id": "MECH_BRIDGE",
                "target_point": {"x": 0, "y": 0},
            }
            echo = client.post(
                "/api/v1/level/rule/cast",
                headers=echo_headers,
                json=echo_payload,
            )
            assert echo.status_code == 200, echo.text
            assert echo.json()["data"]["effects"][0]["mechanism_id"] == "MECH_BRIDGE"

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
                    "target_id": "MECH_BRIDGE",
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
                json={"run_id": first_run, "target_id": "MECH_BRIDGE"},
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
            assert second_state.json()["data"]["mechanisms"] == []

            wrong_order_gaze = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **second["headers"],
                    "Idempotency-Key": "rule-gaze-wrong-order-0001",
                },
                json={
                    "run_id": second_run,
                    "rule_id": "RULE_GAZE",
                    "target_id": "MECH_BRIDGE",
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
                    "target_id": "MECH_BRIDGE",
                    "target_point": {"x": 0, "y": 0},
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
                    "target_id": "MECH_ENERGY_GATE",
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
                    "target_id": "MECH_ENERGY_GATE",
                    "target_point": {"x": 1, "y": 1},
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
            energy = reversed_state.json()["data"]["mechanisms"][0]["state"]
            assert energy["direction"] == -1
            assert energy["reverse_active"] is True

            time.sleep(1.2)
            expired_state = client.get(
                f"/api/v1/level/state/{third_run}", headers=third["headers"]
            )
            energy_after = expired_state.json()["data"]["mechanisms"][0]["state"]
            assert energy_after["direction"] == 1
            assert energy_after["reverse_active"] is False
    finally:
        _set_rule_tuning(False)
        app.dependency_overrides.clear()
