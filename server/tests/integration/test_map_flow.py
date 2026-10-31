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
        return f"map-test-openid-{code}"


def test_two_players_share_map_and_exchange_authoritative_events() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            players = []
            baseline = None
            for index in range(2):
                login = client.post(
                    "/api/v1/auth/login",
                    json={"wx_code": str(uuid4()), "request_id": "map-test-login"},
                )
                assert login.status_code == 200
                token = login.json()["data"]["access_token"]
                headers = {"Authorization": f"Bearer {token}"}
                entered = client.post("/api/v1/map/enter", headers=headers)
                assert entered.status_code == 200
                data = entered.json()["data"]
                if index == 0:
                    # Other tests may already hold presence in this instance, so
                    # the invariant is "each enter adds one", not "the map is
                    # empty when this test starts".
                    baseline = data["current_players"]
                players.append({"token": token, "headers": headers, **data})

            first, second = players
            assert first["instance_id"] == second["instance_id"]
            assert first["spawn_position"] != second["spawn_position"]
            assert second["current_players"] == baseline + 1

            with client.websocket_connect("/api/v1/ws/map") as ws1:
                ws1.send_json({
                    "v": 1, "cmd": "AUTH", "seq": 0, "ts": 0,
                    "payload": {"token": first["token"]},
                })
                assert ws1.receive_json()["cmd"] == "AUTH_OK"
                ws1.send_json({
                    "v": 1, "cmd": "ENTER", "seq": 1, "ts": 0,
                    "payload": {
                        "instance_id": first["instance_id"],
                        "session_id": first["session_id"],
                    },
                })
                assert ws1.receive_json()["cmd"] == "ENTER"

                with client.websocket_connect("/api/v1/ws/map") as ws2:
                    ws2.send_json({
                        "v": 1, "cmd": "AUTH", "seq": 0, "ts": 0,
                        "payload": {"token": second["token"]},
                    })
                    assert ws2.receive_json()["cmd"] == "AUTH_OK"
                    ws2.send_json({
                        "v": 1, "cmd": "ENTER", "seq": 1, "ts": 0,
                        "payload": {
                            "instance_id": second["instance_id"],
                            "session_id": second["session_id"],
                        },
                    })
                    snapshot = ws2.receive_json()
                    assert snapshot["cmd"] == "ENTER"
                    assert len(snapshot["payload"]["players"]) == 1
                    joined = ws1.receive_json()
                    assert joined["cmd"] == "ENTER"

                    ws1.send_json({
                        "v": 1, "cmd": "ACTION_BROADCAST", "seq": 2, "ts": 0,
                        "payload": {"action_id": "ACT_999"},
                    })
                    assert ws1.receive_json()["payload"]["code"] == "ACTION_NOT_ALLOWED"

                    ws1.send_json({
                        "v": 1, "cmd": "ACTION_BROADCAST", "seq": 3, "ts": 0,
                        "payload": {"action_id": "ACT_001"},
                    })
                    action = ws2.receive_json()
                    assert action["cmd"] == "ACTION_BROADCAST"
                    assert action["payload"]["action_id"] == "ACT_001"

                    time.sleep(0.12)
                    spawn = first["spawn_position"]
                    ws1.send_json({
                        "v": 1, "cmd": "MOVE_SYNC", "seq": 4, "ts": 0,
                        "payload": {
                            "x": spawn["x"] + 0.5,
                            "y": spawn["y"],
                            "dir": "E",
                            "client_tick": 100,
                        },
                    })
                    moved = ws2.receive_json()
                    assert moved["cmd"] == "MOVE_SYNC"
                    assert moved["payload"]["player"]["x"] == spawn["x"] + 0.5

                    ws1.send_json({
                        "v": 1, "cmd": "PING", "seq": 5, "ts": 0, "payload": {},
                    })
                    assert ws1.receive_json()["cmd"] == "PONG"

                    ws1.send_json({
                        "v": 1, "cmd": "LEAVE", "seq": 6, "ts": 0, "payload": {},
                    })
                    assert ws1.receive_json()["cmd"] == "LEAVE"
                    assert ws2.receive_json()["cmd"] == "LEAVE"

                    ws2.send_json({
                        "v": 1, "cmd": "LEAVE", "seq": 2, "ts": 0, "payload": {},
                    })
                    assert ws2.receive_json()["cmd"] == "LEAVE"
    finally:
        app.dependency_overrides.clear()
