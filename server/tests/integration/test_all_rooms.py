"""Play every prototype room through the real API and settle it.

ROOM-01 had a full test; ROOM-02..05 and the hidden ending did not, so "five
rooms" was a configuration claim rather than a verified one. Each case here
enters, starts, walks to the mechanism the level's own combo points at, casts
the combo, settles, and asserts the settlement says COMPLETED.

Nothing is stubbed: these go through the same endpoints the client calls.

The rules ship as TUNING_REQUIRED so no invented design value can leak into
production; the `tuned_rules` fixture supplies temporary values and restores the
original state afterwards.
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

SPAWN_X = 1.0
LANE_Y = 4.0


class FakeWeChatProvider:
    async def exchange(self, code: str) -> str:
        return f"rooms-test-openid-{code}"


def _login_and_enter_map(client: TestClient) -> dict:
    login = client.post(
        "/api/v1/auth/login",
        json={"wx_code": str(uuid4()), "request_id": "rooms-test-login"},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.post("/api/v1/map/enter", headers=headers).status_code == 200
    return {"headers": headers}


def _start(client: TestClient, headers: dict, level_id: str) -> str:
    # Entering a level removes the player from the map instance, so every room
    # starts by getting back into the world - exactly what the client does when
    # it returns from a settled room before entering the next one.
    assert client.post("/api/v1/map/enter", headers=headers).status_code == 200
    entered = client.post(
        "/api/v1/level/enter",
        headers={**headers, "Idempotency-Key": f"enter-{level_id}-{uuid4()}"},
        json={"level_id": level_id, "entrance_id": f"ENT-{level_id.split('-', 1)[1]}"},
    )
    assert entered.status_code == 200, entered.text
    run_id = entered.json()["data"]["run_id"]
    started = client.post("/api/v1/level/start", headers=headers, json={"run_id": run_id})
    assert started.status_code == 200, started.text
    return run_id


class Room:
    """One run, with its own position so walks continue from where it stands."""

    def __init__(self, client: TestClient, headers: dict, level_id: str, run_id: str) -> None:
        self.client = client
        self.headers = headers
        self.level_id = level_id
        self.run_id = run_id
        self.x = SPAWN_X

    @classmethod
    def open(cls, client: TestClient, headers: dict, level_id: str) -> "Room":
        return cls(client, headers, level_id, _start(client, headers, level_id))

    def walk_to(self, x: float) -> None:
        step = 1 if x >= self.x else -1
        while abs(self.x - x) > 0.001:
            self.x += step
            # The server allows speed * elapsed + 0.75 per request. Right after
            # /level/start the elapsed time is a few milliseconds, so a one-unit
            # step exceeds the cap; waiting first is what a frame loop does.
            time.sleep(0.12)
            response = self.client.post(
                "/api/v1/level/position",
                headers=self.headers,
                json={"run_id": self.run_id, "x": float(self.x), "y": LANE_Y},
            )
            assert response.status_code == 200, response.text

    def cast(self, rule_id: str, target_id: str, point: dict | None = None) -> None:
        payload = {"run_id": self.run_id, "rule_id": rule_id, "target_id": target_id}
        if point is not None:
            payload["target_point"] = point
        for _ in range(4):
            response = self.client.post(
                "/api/v1/level/rule/cast",
                headers={**self.headers, "Idempotency-Key": f"cast-{uuid4()}"},
                json=payload,
            )
            if response.status_code == 200:
                return
            detail = response.json().get("detail")
            # A rule cools down for a few seconds after each cast. Waiting it out
            # is what a player does, and the combo window is measured between the
            # two casts, so a wait before the first one costs nothing.
            if (
                response.status_code == 409
                and isinstance(detail, dict)
                and detail.get("code") == "RULE_COOLDOWN"
            ):
                time.sleep(detail["remaining_ms"] / 1000 + 0.2)
                continue
            raise AssertionError(f"{rule_id} on {target_id}: {response.text}")
        raise AssertionError(f"{rule_id} on {target_id}: still cooling down after retries")

    def apply_combo(self, mechanism_id: str, x: float, rules: list[str]) -> None:
        """Walk next to the mechanism, then cast the rules in order on it.

        The server matches a combo by two different rule ids cast on the same
        target inside the combo's time window.
        """
        self.walk_to(x)
        for rule_id in rules:
            point = {"x": x, "y": LANE_Y} if rule_id == "RULE_ECHO" else None
            self.cast(rule_id, mechanism_id, point)

    def settle(self) -> dict:
        response = self.client.post(
            "/api/v1/level/settle",
            headers={**self.headers, "Idempotency-Key": f"settle-{uuid4()}"},
            json={"run_id": self.run_id},
        )
        assert response.status_code == 200, response.text
        return response.json()["data"]


def complete_room01(client: TestClient, headers: dict) -> dict:
    """ROOM-01 wants the hidden symbol revealed and the exit triggered."""
    room = Room.open(client, headers, "LV-ROOM-01")
    room.apply_combo("M01-HIDEABLE-01", 5.0, ["RULE_ECHO"])
    room.walk_to(10.0)
    interact = client.post(
        "/api/v1/level/mechanism/interact",
        headers={**headers, "Idempotency-Key": f"exit-{uuid4()}"},
        json={"run_id": room.run_id, "mechanism_id": "M01-EXIT-01"},
    )
    assert interact.status_code == 200, interact.text
    return room.settle()


def complete_room02(client: TestClient, headers: dict) -> dict:
    room = Room.open(client, headers, "LV-ROOM-02")
    room.apply_combo("M02-BRIDGE-01", 6.0, ["RULE_ECHO", "RULE_GAZE"])
    return room.settle()


def complete_room03(client: TestClient, headers: dict) -> dict:
    room = Room.open(client, headers, "LV-ROOM-03")
    room.apply_combo("M03-ENERGY-01", 4.0, ["RULE_ECHO", "RULE_REVERSE"])
    return room.settle()


def complete_room04(client: TestClient, headers: dict) -> dict:
    room = Room.open(client, headers, "LV-ROOM-04")
    room.apply_combo("M04-PLATFORM-01", 4.0, ["RULE_GAZE", "RULE_REVERSE"])
    return room.settle()


def complete_room05(client: TestClient, headers: dict) -> dict:
    room = Room.open(client, headers, "LV-ROOM-05")
    room.apply_combo("M05-BRIDGE-01", 3.0, ["RULE_ECHO", "RULE_GAZE"])
    room.apply_combo("M05-ENERGY-01", 6.0, ["RULE_ECHO", "RULE_REVERSE"])
    room.apply_combo("M05-REVERSE-01", 9.0, ["RULE_GAZE", "RULE_REVERSE"])
    return room.settle()


@pytest.fixture()
def client(tuned_rules: None):
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_room01_reveal_and_exit(client: TestClient) -> None:
    player = _login_and_enter_map(client)
    result = complete_room01(client, player["headers"])
    assert result["result_status"] == "COMPLETED", result


def test_room02_bridge_combo_completes_the_room(client: TestClient) -> None:
    player = _login_and_enter_map(client)
    result = complete_room02(client, player["headers"])
    assert result["result_status"] == "COMPLETED", result
    assert result["level_id"] == "LV-ROOM-02"


def test_room03_energy_combo_opens_the_door(client: TestClient) -> None:
    player = _login_and_enter_map(client)
    result = complete_room03(client, player["headers"])
    assert result["result_status"] == "COMPLETED", result


def test_room04_gaze_then_reverse_locks_the_platform(client: TestClient) -> None:
    player = _login_and_enter_map(client)
    result = complete_room04(client, player["headers"])
    assert result["result_status"] == "COMPLETED", result


def test_room05_needs_all_three_combos(client: TestClient) -> None:
    player = _login_and_enter_map(client)
    room = Room.open(client, player["headers"], "LV-ROOM-05")
    room.apply_combo("M05-BRIDGE-01", 3.0, ["RULE_ECHO", "RULE_GAZE"])

    # Settling after one combo must be refused: the level records three required
    # objectives of its own.
    early = client.post(
        "/api/v1/level/settle",
        headers={**player["headers"], "Idempotency-Key": f"early-{uuid4()}"},
        json={"run_id": room.run_id},
    )
    assert early.status_code == 409, early.text

    room.apply_combo("M05-ENERGY-01", 6.0, ["RULE_ECHO", "RULE_REVERSE"])
    room.apply_combo("M05-REVERSE-01", 9.0, ["RULE_GAZE", "RULE_REVERSE"])
    result = room.settle()
    assert result["result_status"] == "COMPLETED", result


def test_hidden_ending_is_locked_until_all_five_rooms_are_cleared(client: TestClient) -> None:
    """The gate is real: the route needs ROOM-01..05 completed and the ROOM-05
    combo sequence, so a fresh player must be refused."""
    player = _login_and_enter_map(client)
    refused = client.post(
        "/api/v1/level/enter",
        headers={**player["headers"], "Idempotency-Key": f"hidden-{uuid4()}"},
        json={"level_id": "LV-HIDDEN-01", "entrance_id": "ENT-HIDDEN-01"},
    )
    assert refused.status_code == 403, refused.text


def test_five_rooms_unlock_the_hidden_ending(client: TestClient) -> None:
    player = _login_and_enter_map(client)
    for complete in (
        complete_room01,
        complete_room02,
        complete_room03,
        complete_room04,
        complete_room05,
    ):
        result = complete(client, player["headers"])
        assert result["result_status"] == "COMPLETED", result

    # ROOM-05's own enter took the player out of the map, and the hidden level is
    # entered from the shared map, so get back in first.
    assert client.post(
        "/api/v1/map/enter", headers=player["headers"]
    ).status_code == 200

    entered = client.post(
        "/api/v1/level/enter",
        headers={**player["headers"], "Idempotency-Key": f"hidden-{uuid4()}"},
        json={"level_id": "LV-HIDDEN-01", "entrance_id": "ENT-HIDDEN-01"},
    )
    assert entered.status_code == 200, entered.text

    room = Room(
        client, player["headers"], "LV-HIDDEN-01", entered.json()["data"]["run_id"]
    )
    assert client.post(
        "/api/v1/level/start", headers=player["headers"], json={"run_id": room.run_id}
    ).status_code == 200
    room.walk_to(9.0)

    interact = client.post(
        "/api/v1/level/mechanism/interact",
        headers={**player["headers"], "Idempotency-Key": f"ending-{uuid4()}"},
        json={"run_id": room.run_id, "mechanism_id": "H01-END"},
    )
    assert interact.status_code == 200, interact.text
    assert interact.json()["data"]["state"]["status"] == "TRIGGERED"
    result = room.settle()
    assert result["result_status"] == "COMPLETED", result
    assert result["level_id"] == "LV-HIDDEN-01"
