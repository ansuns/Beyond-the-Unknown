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

            abandoned = client.post(
                "/api/v1/level/abandon",
                headers=first["headers"],
                json={"run_id": first_data["run_id"]},
            )
            assert abandoned.status_code == 200
            assert abandoned.json()["data"]["status"] == "ABANDONED"

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
            assert [room["room_index"] for room in rooms if not room["is_hidden"]] == [1, 2, 3, 4, 5]
    finally:
        app.dependency_overrides.clear()
