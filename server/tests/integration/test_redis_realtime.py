import asyncio
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from app.realtime.manager import MapConnectionManager

REDIS_URL = os.getenv("TEST_REDIS_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not REDIS_URL, reason="Set TEST_REDIS_URL to run Redis integration tests"),
]


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.closed_code: int | None = None
        self.scope = {"state": {}}

    async def send_json(self, message: dict) -> None:
        self.messages.append(message)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        self.closed_code = code


async def wait_for_command(
    websocket: FakeWebSocket, command: str, after: int = 0
) -> dict:
    for _ in range(50):
        matches = [message for message in websocket.messages[after:] if message["cmd"] == command]
        if matches:
            return matches[-1]
        await asyncio.sleep(0.02)
    raise AssertionError(f"Timed out waiting for WebSocket command {command}")


def test_two_api_nodes_share_presence_and_fanout_with_connection_lease() -> None:
    async def run() -> None:
        instance_id = f"redis-test-{uuid4()}"
        first_client = Redis.from_url(REDIS_URL, decode_responses=True)
        second_client = Redis.from_url(REDIS_URL, decode_responses=True)
        first = MapConnectionManager(first_client, node_id="node-a", owns_redis_client=True)
        second = MapConnectionManager(second_client, node_id="node-b", owns_redis_client=True)
        first_socket = FakeWebSocket()
        second_socket = FakeWebSocket()
        replacement_socket = FakeWebSocket()
        avatar_one = {
            "player_id": "player-1",
            "character_id": "CHAR_001",
            "x": 0.0,
            "y": 0.0,
            "direction": "S",
        }
        avatar_two = {
            "player_id": "player-2",
            "character_id": "CHAR_002",
            "x": 2.0,
            "y": 0.0,
            "direction": "W",
        }
        try:
            await first.start(presence_ttl_seconds=30)
            await second.start(presence_ttl_seconds=30)
            first_lease = await first.attach(
                first_socket, instance_id, "player-1", avatar_one
            )
            await second.attach(second_socket, instance_id, "player-2", avatar_two)

            second_enter = await wait_for_command(second_socket, "ENTER")
            assert second_enter["payload"]["players"] == [avatar_one]
            await wait_for_command(first_socket, "ENTER")

            first_before = len(second_socket.messages)
            await first.update_avatar(
                instance_id, "player-1", {"x": 0.75, "direction": "E"}
            )
            move = await wait_for_command(
                second_socket, "MOVE_SYNC", after=first_before
            )
            assert move["payload"]["player"]["x"] == 0.75

            replacement_lease = await second.attach(
                replacement_socket, instance_id, "player-1", avatar_one
            )
            assert await first.is_owner(instance_id, "player-1", first_lease) is False
            assert await second.is_owner(
                instance_id, "player-1", replacement_lease
            ) is True
            assert await first.detach(
                first_socket, instance_id, "player-1"
            ) is False
            # A delayed cleanup from the superseded socket must not delete the new lease.
            await first.remove_avatar(instance_id, "player-1", first_lease)
            assert await second.is_owner(
                instance_id, "player-1", replacement_lease
            ) is True
            assert await first_client.get(
                first._owner_key(instance_id, "player-1")
            ) == replacement_lease

            await second.remove_avatar(
                instance_id, "player-1", replacement_lease
            )
            leave = await wait_for_command(second_socket, "LEAVE")
            assert leave["payload"]["player_id"] == "player-1"
        finally:
            await first.close()
            await second.close()

    asyncio.run(run())
