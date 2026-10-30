import pytest

from app.realtime.manager import MapConnectionManager


class FakeWebSocket:
    def __init__(self):
        self.messages = []
        self.closed_code = None
        self.scope = {"state": {}}

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, code=1000):
        self.closed_code = code


@pytest.mark.asyncio
async def test_manager_snapshots_broadcasts_and_removes_players():
    manager = MapConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()

    await manager.attach(
        first, "instance-1", "player-1",
        {"player_id": "player-1", "x": 0.0, "y": 0.0, "direction": "S"},
    )
    await manager.attach(
        second, "instance-1", "player-2",
        {"player_id": "player-2", "x": 2.0, "y": 0.0, "direction": "S"},
    )

    assert first.messages[0]["cmd"] == "ENTER"
    assert second.messages[0]["cmd"] == "ENTER"
    assert second.messages[0]["payload"]["players"][0]["player_id"] == "player-1"
    assert first.messages[-1]["cmd"] == "ENTER"

    await manager.update_avatar(
        "instance-1", "player-1", {"x": 0.5, "direction": "E"}
    )
    assert second.messages[-1]["cmd"] == "MOVE_SYNC"
    assert second.messages[-1]["payload"]["player"]["x"] == 0.5

    await manager.broadcast(
        "instance-1", "player-1", "ACTION_BROADCAST",
        {"player_id": "player-1", "action_id": "ACT_001"},
    )
    assert second.messages[-1]["cmd"] == "ACTION_BROADCAST"

    await manager.remove_avatar("instance-1", "player-1")
    assert second.messages[-1]["cmd"] == "LEAVE"


@pytest.mark.asyncio
async def test_reconnecting_player_replaces_old_socket_without_old_socket_detaching_new():
    manager = MapConnectionManager()
    old_socket = FakeWebSocket()
    new_socket = FakeWebSocket()
    avatar = {"player_id": "player-1", "x": 0.0, "y": 0.0, "direction": "S"}

    await manager.attach(old_socket, "instance-1", "player-1", avatar)
    await manager.attach(new_socket, "instance-1", "player-1", avatar)

    assert old_socket.closed_code == 4001
    assert await manager.detach(old_socket, "instance-1", "player-1") is False
    assert await manager.detach(new_socket, "instance-1", "player-1") is True


@pytest.mark.asyncio
async def test_evict_player_closes_socket_and_broadcasts_leave():
    manager = MapConnectionManager()
    player_socket = FakeWebSocket()
    observer_socket = FakeWebSocket()
    avatar = {"player_id": "player-1", "x": 0.0, "y": 0.0, "direction": "S"}
    await manager.attach(player_socket, "instance-1", "player-1", avatar)
    await manager.attach(
        observer_socket,
        "instance-1",
        "player-2",
        {"player_id": "player-2", "x": 2.0, "y": 0.0, "direction": "S"},
    )

    await manager.evict_player("instance-1", "player-1")

    assert player_socket.closed_code == 4002
    assert await manager.avatar("instance-1", "player-1") is None
    assert observer_socket.messages[-1]["cmd"] == "LEAVE"
