# ruff: noqa: I001

import os
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


def test_personal_laws_are_authoritative_idempotent_and_combo_aware(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "law_combo_window_ms", 60_000)
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            first = _login_and_enter_map(client)
            second = _login_and_enter_map(client)

            entered = client.post(
                "/api/v1/level/enter",
                headers={**first["headers"], "Idempotency-Key": "law-room-one-enter-0001"},
                json={"level_id": "LV-ROOM-01", "entrance_id": "ENT-ROOM-01"},
            )
            assert entered.status_code == 200
            run_id = entered.json()["data"]["run_id"]
            started = client.post(
                "/api/v1/level/start",
                headers=first["headers"],
                json={"run_id": run_id},
            )
            assert started.status_code == 200

            echo_headers = {
                **first["headers"],
                "Idempotency-Key": "law-echo-room-one-0001",
            }
            echo_payload = {
                "run_id": run_id,
                "rule_id": "RULE_ECHO",
                "mechanism_id": "M01-HIDEABLE-01",
                "action": "APPLY",
            }
            echo = client.post(
                "/api/v1/level/law/action",
                headers=echo_headers,
                json=echo_payload,
            )
            assert echo.status_code == 200
            assert echo.json()["data"]["state"]["state"] == "REVEALED"

            replay = client.post(
                "/api/v1/level/law/action",
                headers=echo_headers,
                json=echo_payload,
            )
            assert replay.status_code == 200
            assert replay.json()["data"]["idempotent_replay"] is True

            conflict = client.post(
                "/api/v1/level/law/action",
                headers=echo_headers,
                json={**echo_payload, "rule_id": "RULE_REVERSE"},
            )
            assert conflict.status_code == 409

            foreign_state = client.get(
                f"/api/v1/level/runs/{run_id}/mechanisms",
                headers=second["headers"],
            )
            assert foreign_state.status_code == 404

            state = client.get(
                f"/api/v1/level/runs/{run_id}/mechanisms",
                headers=first["headers"],
            )
            assert state.status_code == 200
            assert any(
                item["mechanism_id"] == "M01-HIDEABLE-01"
                and item["state"]["state"] == "REVEALED"
                for item in state.json()["data"]["mechanisms"]
            )

            abandoned = client.post(
                "/api/v1/level/abandon",
                headers=first["headers"],
                json={"run_id": run_id},
            )
            assert abandoned.status_code == 200
            returned = client.post("/api/v1/map/enter", headers=first["headers"])
            assert returned.status_code == 200

            room_two = client.post(
                "/api/v1/level/enter",
                headers={**first["headers"], "Idempotency-Key": "law-room-two-enter-0001"},
                json={"level_id": "LV-ROOM-02", "entrance_id": "ENT-ROOM-02"},
            )
            assert room_two.status_code == 200
            run_two = room_two.json()["data"]["run_id"]
            assert client.post(
                "/api/v1/level/start",
                headers=first["headers"],
                json={"run_id": run_two},
            ).status_code == 200

            echo_bridge = client.post(
                "/api/v1/level/law/action",
                headers={**first["headers"], "Idempotency-Key": "law-room-two-echo-0001"},
                json={
                    "run_id": run_two,
                    "rule_id": "RULE_ECHO",
                    "mechanism_id": "M02-BRIDGE-01",
                    "action": "APPLY",
                },
            )
            assert echo_bridge.status_code == 200
            gaze_bridge = client.post(
                "/api/v1/level/law/action",
                headers={**first["headers"], "Idempotency-Key": "law-room-two-gaze-0001"},
                json={
                    "run_id": run_two,
                    "rule_id": "RULE_GAZE",
                    "mechanism_id": "M02-BRIDGE-01",
                    "action": "APPLY",
                },
            )
            assert gaze_bridge.status_code == 200
            assert gaze_bridge.json()["data"]["combo_id"] == "COMBO-001"
            assert gaze_bridge.json()["data"]["state"]["state"] == "OPEN"
    finally:
        app.dependency_overrides.clear()
