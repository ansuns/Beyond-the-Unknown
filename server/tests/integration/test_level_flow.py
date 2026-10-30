# ruff: noqa: I001

import os
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.provider import get_wechat_code_provider


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL and apply Alembic migrations for PostgreSQL integration tests",
)


class FakeWeChatProvider:
    async def exchange(self, code: str) -> str:
        return f"level-test-openid-{code}"


def _login_and_enter_map(client: TestClient) -> dict:
    login = client.post(
        "/api/v1/auth/login",
        json={"wx_code": str(uuid4()), "request_id": "level-test-login"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    entered = client.post("/api/v1/map/enter", headers=headers)
    assert entered.status_code == 200
    return {"headers": headers, "map": entered.json()["data"]}


def test_personal_level_run_entry_is_idempotent_and_isolated() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            first = _login_and_enter_map(client)
            second = _login_and_enter_map(client)

            first_headers = {
                **first["headers"],
                "Idempotency-Key": "level-enter-first-0001",
            }
            first_enter = client.post(
                "/api/v1/level/enter",
                headers=first_headers,
                json={"level_id": "LV-ROOM-01", "entrance_id": "ENT-ROOM-01"},
            )
            assert first_enter.status_code == 200
            first_data = first_enter.json()["data"]
            assert first_data["status"] == "CREATED"
            assert first_data["level"]["room_index"] == 1

            replay = client.post(
                "/api/v1/level/enter",
                headers=first_headers,
                json={"level_id": "LV-ROOM-01", "entrance_id": "ENT-ROOM-01"},
            )
            assert replay.status_code == 200
            assert replay.json()["data"]["run_id"] == first_data["run_id"]
            assert replay.json()["data"]["idempotent_replay"] is True

            conflict = client.post(
                "/api/v1/level/enter",
                headers=first_headers,
                json={"level_id": "LV-ROOM-02", "entrance_id": "ENT-ROOM-02"},
            )
            assert conflict.status_code == 409

            started = client.post(
                "/api/v1/level/start",
                headers=first["headers"],
                json={"run_id": first_data["run_id"]},
            )
            assert started.status_code == 200
            assert started.json()["data"]["status"] == "RUNNING"

            active_conflict = client.post(
                "/api/v1/level/enter",
                headers={**first["headers"], "Idempotency-Key": "level-enter-active-0001"},
                json={"level_id": "LV-ROOM-02", "entrance_id": "ENT-ROOM-02"},
            )
            assert active_conflict.status_code == 409

            cross_player = client.post(
                "/api/v1/level/start",
                headers=second["headers"],
                json={"run_id": first_data["run_id"]},
            )
            assert cross_player.status_code == 404

            abandoned = client.post(
                "/api/v1/level/abandon",
                headers=first["headers"],
                json={"run_id": first_data["run_id"]},
            )
            assert abandoned.status_code == 200
            assert abandoned.json()["data"]["status"] == "ABANDONED"

            returned_to_map = client.post("/api/v1/map/enter", headers=first["headers"])
            assert returned_to_map.status_code == 200

            second_enter = client.post(
                "/api/v1/level/enter",
                headers={**second["headers"], "Idempotency-Key": "level-enter-second-0001"},
                json={"level_id": "LV-ROOM-01", "entrance_id": "ENT-ROOM-01"},
            )
            assert second_enter.status_code == 200
            assert second_enter.json()["data"]["run_id"] != first_data["run_id"]

            hidden = client.post(
                "/api/v1/level/enter",
                headers={
                    **second["headers"],
                    "Idempotency-Key": "level-enter-hidden-0001",
                },
                json={"level_id": "LV-HIDDEN-01", "entrance_id": "ENT-HIDDEN-01"},
            )
            assert hidden.status_code == 403

            levels = client.get("/api/v1/level/", headers=first["headers"])
            assert levels.status_code == 200
            rooms = levels.json()["data"]["levels"]
            assert [
                room["room_index"] for room in rooms if not room["is_hidden"]
            ] == [1, 2, 3, 4, 5]

            cleanup = client.post(
                "/api/v1/level/enter",
                headers={
                    **first["headers"],
                    "Idempotency-Key": "level-enter-cleanup-0001",
                },
                json={"level_id": "LV-ROOM-02", "entrance_id": "ENT-ROOM-02"},
            )
            assert cleanup.status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_room01_echo_exit_interaction_and_settlement() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            player = _login_and_enter_map(client)
            entered = client.post(
                "/api/v1/level/enter",
                headers={
                    **player["headers"],
                    "Idempotency-Key": f"room01-enter-{uuid4()}",
                },
                json={"level_id": "LV-ROOM-01", "entrance_id": "ENT-ROOM-01"},
            )
            assert entered.status_code == 200, entered.text
            run_id = entered.json()["data"]["run_id"]
            started = client.post(
                "/api/v1/level/start",
                headers=player["headers"],
                json={"run_id": run_id},
            )
            assert started.status_code == 200, started.text

            outside = client.post(
                "/api/v1/level/position",
                headers=player["headers"],
                json={"run_id": run_id, "x": 13, "y": 4},
            )
            assert outside.status_code == 422
            teleport = client.post(
                "/api/v1/level/position",
                headers=player["headers"],
                json={"run_id": run_id, "x": 10.5, "y": 4},
            )
            assert teleport.status_code == 422

            at_exit = None
            for x in range(2, 6):
                time.sleep(0.1)
                at_exit = client.post(
                    "/api/v1/level/position",
                    headers=player["headers"],
                    json={"run_id": run_id, "x": float(x), "y": 4},
                )
                assert at_exit.status_code == 200, at_exit.text

            # The Echo target point must remain within range of the authoritative
            # player position; a client cannot cast across the entire room.
            far_echo = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **player["headers"],
                    "Idempotency-Key": "room01-echo-far-0001",
                },
                json={
                    "run_id": run_id,
                    "rule_id": "RULE_ECHO",
                    "target_id": "M01-HIDEABLE-01",
                    "target_point": {"x": 10.5, "y": 4},
                },
            )
            assert far_echo.status_code == 422

            locked_exit = client.post(
                "/api/v1/level/mechanism/interact",
                headers={
                    **player["headers"],
                    "Idempotency-Key": "room01-exit-before-echo-001",
                },
                json={"run_id": run_id, "mechanism_id": "M01-EXIT-01"},
            )
            assert locked_exit.status_code == 409

            echo = client.post(
                "/api/v1/level/rule/cast",
                headers={
                    **player["headers"],
                    "Idempotency-Key": "room01-echo-hidden-0001",
                },
                json={
                    "run_id": run_id,
                    "rule_id": "RULE_ECHO",
                    "target_id": "M01-HIDEABLE-01",
                    "target_point": {"x": 5, "y": 4},
                },
            )
            assert echo.status_code == 200, echo.text
            assert echo.json()["data"]["effects"][0]["mechanism_id"] == "M01-HIDEABLE-01"

            for x in range(6, 11):
                time.sleep(0.1)
                at_exit = client.post(
                    "/api/v1/level/position",
                    headers=player["headers"],
                    json={"run_id": run_id, "x": float(x), "y": 4},
                )
                assert at_exit.status_code == 200, at_exit.text

            opened = client.post(
                "/api/v1/level/mechanism/interact",
                headers={
                    **player["headers"],
                    "Idempotency-Key": "room01-exit-interact-0001",
                },
                json={"run_id": run_id, "mechanism_id": "M01-EXIT-01"},
            )
            assert opened.status_code == 200, opened.text
            assert opened.json()["data"]["state"]["status"] == "TRIGGERED"

            replay = client.post(
                "/api/v1/level/mechanism/interact",
                headers={
                    **player["headers"],
                    "Idempotency-Key": "room01-exit-interact-0001",
                },
                json={"run_id": run_id, "mechanism_id": "M01-EXIT-01"},
            )
            assert replay.status_code == 200
            assert replay.json()["data"]["idempotent_replay"] is True

            settled = client.post(
                "/api/v1/level/settle",
                headers={
                    **player["headers"],
                    "Idempotency-Key": "room01-settle-0001",
                },
                json={"run_id": run_id},
            )
            assert settled.status_code == 200, settled.text
            assert settled.json()["data"]["result_status"] == "COMPLETED"
    finally:
        app.dependency_overrides.clear()
