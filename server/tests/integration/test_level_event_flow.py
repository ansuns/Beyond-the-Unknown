"""The three room event sources must actually move the tutorial task.

Before this pipeline existed the objectives were defined in
``task_catalog.json`` but nothing ever advanced LOGIN, MOVE or RULE_CAST, so a
player could finish the room and still see four empty objectives. These tests
pin the behaviour that fixes it, including the duplicate-report and isolation
requirements from GDD 11.1.
"""

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
        return f"level-events-openid-{code}"


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"wx_code": str(uuid4()), "request_id": f"events-login-{uuid4()}"},
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['data']['access_token']}"}
    entered = client.post("/api/v1/map/enter", headers=headers)
    assert entered.status_code == 200, entered.text
    return {"headers": headers, "map": entered.json()["data"]}


def _objectives(client: TestClient, headers: dict) -> dict[str, int]:
    response = client.get("/api/v1/player/tasks", headers=headers)
    assert response.status_code == 200, response.text
    task = response.json()["data"]["tasks"][0]
    return {
        objective["objective_type"]: objective["current_value"]
        for objective in task["objectives"]
    }


def _enter_room01(client: TestClient, headers: dict) -> str:
    entered = client.post(
        "/api/v1/level/enter",
        headers={**headers, "Idempotency-Key": f"events-enter-{uuid4()}"},
        json={"level_id": "LV-ROOM-01", "entrance_id": "ENT-ROOM-01"},
    )
    assert entered.status_code == 200, entered.text
    run_id = entered.json()["data"]["run_id"]
    started = client.post("/api/v1/level/start", headers=headers, json={"run_id": run_id})
    assert started.status_code == 200, started.text
    return run_id


def _walk(client: TestClient, headers: dict, run_id: str, positions: range) -> None:
    """Step one tile at a time; the server caps distance by elapsed time."""
    for x in positions:
        time.sleep(0.12)
        moved = client.post(
            "/api/v1/level/position",
            headers=headers,
            json={"run_id": run_id, "x": float(x), "y": 4},
        )
        assert moved.status_code == 200, moved.text


def _complete_room01(client: TestClient, headers: dict, run_id: str) -> None:
    """Walk to the hidden object, reveal it with Echo, then open the exit."""
    _walk(client, headers, run_id, range(2, 11))
    # Echo can only reach two units, so the cast has to happen next to the
    # hidden object rather than from the far side of the room.
    _walk(client, headers, run_id, range(9, 4, -1))

    echo = client.post(
        "/api/v1/level/rule/cast",
        headers={**headers, "Idempotency-Key": f"events-echo-{uuid4()}"},
        json={
            "run_id": run_id,
            "rule_id": "RULE_ECHO",
            "target_id": "M01-HIDEABLE-01",
            "target_point": {"x": 5, "y": 4},
        },
    )
    assert echo.status_code == 200, echo.text

    _walk(client, headers, run_id, range(6, 11))

    opened = client.post(
        "/api/v1/level/mechanism/interact",
        headers={**headers, "Idempotency-Key": f"events-exit-{uuid4()}"},
        json={"run_id": run_id, "mechanism_id": "M01-EXIT-01"},
    )
    assert opened.status_code == 200, opened.text

    settled = client.post(
        "/api/v1/level/settle",
        headers={**headers, "Idempotency-Key": f"events-settle-{uuid4()}"},
        json={"run_id": run_id},
    )
    assert settled.status_code == 200, settled.text
    assert settled.json()["data"]["result_status"] == "COMPLETED"


def test_login_alone_advances_the_first_objective_only() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            # The same wx_code means the same account, so the second login is a
            # repeat of the same event rather than a new player.
            code = str(uuid4())
            first = client.post(
                "/api/v1/auth/login",
                json={"wx_code": code, "request_id": f"events-login-{uuid4()}"},
            )
            assert first.status_code == 200, first.text
            headers = {"Authorization": f"Bearer {first.json()['data']['access_token']}"}
            assert _objectives(client, headers) == {
                "LOGIN": 1,
                "MOVE": 0,
                "RULE_CAST": 0,
                "SETTLEMENT": 0,
            }

            again = client.post(
                "/api/v1/auth/login",
                json={"wx_code": code, "request_id": f"events-login-{uuid4()}"},
            )
            assert again.status_code == 200, again.text
            repeated = {"Authorization": f"Bearer {again.json()['data']['access_token']}"}
            assert _objectives(client, repeated)["LOGIN"] == 1
    finally:
        app.dependency_overrides.clear()


def test_moving_advances_move_once_per_run_even_if_the_packet_repeats() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            player = _login(client)
            run_id = _enter_room01(client, player["headers"])

            _walk(client, player["headers"], run_id, range(2, 4))
            assert _objectives(client, player["headers"])["MOVE"] == 1

            # Re-send the exact same position several times: the objective is
            # already met and must not tick further.
            for _ in range(3):
                moved = client.post(
                    "/api/v1/level/position",
                    headers=player["headers"],
                    json={"run_id": run_id, "x": 3.0, "y": 4.0},
                )
                assert moved.status_code == 200, moved.text
            assert _objectives(client, player["headers"])["MOVE"] == 1
    finally:
        app.dependency_overrides.clear()


def test_rule_cast_and_settlement_complete_the_tutorial(tuned_rules: None) -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            player = _login(client)
            run_id = _enter_room01(client, player["headers"])
            _complete_room01(client, player["headers"], run_id)

            objectives = _objectives(client, player["headers"])
            assert objectives == {
                "LOGIN": 1,
                "MOVE": 1,
                "RULE_CAST": 1,
                "SETTLEMENT": 1,
            }

            tasks = client.get("/api/v1/player/tasks", headers=player["headers"]).json()["data"][
                "tasks"
            ]
            assert tasks[0]["status"] == "COMPLETED"
    finally:
        app.dependency_overrides.clear()


def test_objectives_are_isolated_between_players() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            first = _login(client)
            second = _login(client)

            run_id = _enter_room01(client, first["headers"])
            _walk(client, first["headers"], run_id, range(2, 4))

            assert _objectives(client, first["headers"])["MOVE"] == 1
            assert _objectives(client, second["headers"])["MOVE"] == 0
    finally:
        app.dependency_overrides.clear()
