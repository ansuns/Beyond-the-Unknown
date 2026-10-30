import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket


@dataclass
class Connection:
    websocket: WebSocket
    instance_id: str
    player_id: str
    server_seq: int = 0


class MapConnectionManager:
    def __init__(self) -> None:
        self.connections: dict[tuple[str, str], Connection] = {}
        self.avatars: dict[tuple[str, str], dict[str, Any]] = {}
        self.lock = asyncio.Lock()

    @staticmethod
    def message(command: str, payload: dict[str, Any], seq: int = 0) -> dict[str, Any]:
        return {
            "v": 1,
            "cmd": command,
            "seq": seq,
            "ts": int(datetime.now(UTC).timestamp() * 1000),
            "payload": payload,
        }

    async def _send(self, connection: Connection, command: str, payload: dict[str, Any]) -> None:
        state = connection.websocket.scope.setdefault("state", {})
        connection.server_seq = max(connection.server_seq, state.get("server_seq", 0)) + 1
        state["server_seq"] = connection.server_seq
        await connection.websocket.send_json(
            self.message(command, payload, connection.server_seq)
        )

    async def broadcast(
        self, instance_id: str, sender_id: str, command: str, payload: dict[str, Any]
    ) -> None:
        targets = [
            connection
            for (current_instance, player_id), connection in list(self.connections.items())
            if current_instance == instance_id and player_id != sender_id
        ]
        for connection in targets:
            try:
                await self._send(connection, command, payload)
            except Exception:
                await self.detach(connection.websocket, instance_id, connection.player_id)

    async def attach(
        self,
        websocket: WebSocket,
        instance_id: str,
        player_id: str,
        avatar: dict[str, Any],
    ) -> None:
        key = (instance_id, player_id)
        async with self.lock:
            old = self.connections.get(key)
            snapshot = [
                value.copy()
                for (current_instance, current_player), value in self.avatars.items()
                if current_instance == instance_id and current_player != player_id
            ]
            self.connections[key] = Connection(
                websocket, instance_id, player_id,
                server_seq=websocket.scope.setdefault("state", {}).get("server_seq", 0),
            )
            self.avatars[key] = avatar
        if old is not None and old.websocket is not websocket:
            try:
                await old.websocket.close(code=4001)
            except Exception:
                pass
        connection = self.connections[key]
        await self._send(connection, "ENTER", {"instance_id": instance_id, "players": snapshot})
        await self.broadcast(instance_id, player_id, "ENTER", {"player": avatar})

    async def detach(self, websocket: WebSocket, instance_id: str, player_id: str) -> bool:
        key = (instance_id, player_id)
        async with self.lock:
            current = self.connections.get(key)
            if current is None or current.websocket is not websocket:
                return False
            self.connections.pop(key, None)
            return True

    async def update_avatar(
        self, instance_id: str, player_id: str, values: dict[str, Any]
    ) -> None:
        key = (instance_id, player_id)
        async with self.lock:
            avatar = self.avatars.get(key)
            if avatar is None:
                return
            avatar.update(values)
            payload = avatar.copy()
        await self.broadcast(instance_id, player_id, "MOVE_SYNC", {"player": payload})

    async def avatar(self, instance_id: str, player_id: str) -> dict[str, Any] | None:
        async with self.lock:
            value = self.avatars.get((instance_id, player_id))
            return value.copy() if value else None

    async def remove_avatar(self, instance_id: str, player_id: str) -> None:
        key = (instance_id, player_id)
        async with self.lock:
            self.connections.pop(key, None)
            existed = self.avatars.pop(key, None) is not None
        if existed:
            await self.broadcast(instance_id, player_id, "LEAVE", {"player_id": player_id})


    async def evict_player(self, instance_id: str, player_id: str) -> None:
        key = (instance_id, player_id)
        async with self.lock:
            connection = self.connections.pop(key, None)
            existed = self.avatars.pop(key, None) is not None
        if connection is not None:
            try:
                await connection.websocket.close(code=4002, reason="Entered personal level")
            except Exception:
                pass
        if existed:
            await self.broadcast(instance_id, player_id, "LEAVE", {"player_id": player_id})


map_connections = MapConnectionManager()
