import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import WebSocket
from redis.asyncio import Redis


@dataclass
class Connection:
    websocket: WebSocket
    instance_id: str
    player_id: str
    lease_token: str
    server_seq: int = 0


class MapConnectionManager:
    _REFRESH_SCRIPT = """
        if redis.call('GET', KEYS[1]) ~= ARGV[1] then
            return 0
        end
        redis.call('ZADD', KEYS[2], ARGV[2], ARGV[3])
        redis.call('EXPIRE', KEYS[2], ARGV[4])
        redis.call('SET', KEYS[3], ARGV[5], 'EX', ARGV[4])
        redis.call('EXPIRE', KEYS[1], ARGV[4])
        return 1
    """
    _RELEASE_SCRIPT = """
        if redis.call('GET', KEYS[1]) == ARGV[1] then
            redis.call('DEL', KEYS[1], KEYS[3])
            redis.call('ZREM', KEYS[2], ARGV[2])
            return 1
        end
        return 0
    """

    def __init__(
        self,
        redis_client: Redis | None = None,
        node_id: str | None = None,
        owns_redis_client: bool = False,
    ) -> None:
        self.connections: dict[tuple[str, str], Connection] = {}
        self.avatars: dict[tuple[str, str], dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        self.redis = redis_client
        self.node_id = node_id or uuid4().hex
        self.presence_ttl_seconds = 90
        self.pubsub = None
        self.listener_task: asyncio.Task | None = None
        self.owns_redis_client = owns_redis_client

    async def start(
        self,
        redis_url: str | None = None,
        presence_ttl_seconds: int = 90,
    ) -> None:
        self.presence_ttl_seconds = max(presence_ttl_seconds, 30)
        if self.redis is None:
            if not redis_url:
                raise ValueError("redis_url is required when no Redis client is injected")
            self.redis = Redis.from_url(redis_url, decode_responses=True)
            self.owns_redis_client = True
        await self.redis.ping()
        self.pubsub = self.redis.pubsub()
        await self.pubsub.psubscribe("map:events:*")
        self.listener_task = asyncio.create_task(self._listen_for_remote_events())

    async def close(self) -> None:
        if self.listener_task is not None:
            self.listener_task.cancel()
            try:
                await self.listener_task
            except asyncio.CancelledError:
                pass
            self.listener_task = None
        if self.pubsub is not None:
            await self.pubsub.aclose()
            self.pubsub = None
        if self.redis is not None and self.owns_redis_client:
            await self.redis.aclose()
            self.redis = None

    async def ping(self) -> bool:
        if self.redis is None:
            return True
        return bool(await self.redis.ping())

    @staticmethod
    def message(command: str, payload: dict[str, Any], seq: int = 0) -> dict[str, Any]:
        return {
            "v": 1,
            "cmd": command,
            "seq": seq,
            "ts": int(datetime.now(UTC).timestamp() * 1000),
            "payload": payload,
        }

    @staticmethod
    def _presence_key(instance_id: str) -> str:
        return f"map:presence:{instance_id}"

    @staticmethod
    def _avatar_key(instance_id: str, player_id: str) -> str:
        return f"map:avatar:{instance_id}:{player_id}"

    @staticmethod
    def _owner_key(instance_id: str, player_id: str) -> str:
        return f"map:owner:{instance_id}:{player_id}"

    async def _send(self, connection: Connection, command: str, payload: dict[str, Any]) -> None:
        state = connection.websocket.scope.setdefault("state", {})
        connection.server_seq = max(connection.server_seq, state.get("server_seq", 0)) + 1
        state["server_seq"] = connection.server_seq
        await connection.websocket.send_json(
            self.message(command, payload, connection.server_seq)
        )

    async def _store_presence(
        self,
        instance_id: str,
        player_id: str,
        avatar: dict[str, Any],
        lease_token: str,
    ) -> None:
        if self.redis is None:
            return
        ttl = self.presence_ttl_seconds
        pipeline = self.redis.pipeline()
        pipeline.zadd(
            self._presence_key(instance_id),
            {player_id: time.time() + ttl},
        )
        pipeline.expire(self._presence_key(instance_id), ttl * 2)
        pipeline.set(
            self._avatar_key(instance_id, player_id),
            json.dumps(avatar, separators=(",", ":")),
            ex=ttl,
        )
        pipeline.set(self._owner_key(instance_id, player_id), lease_token, ex=ttl)
        await pipeline.execute()

    async def _refresh_presence(
        self,
        instance_id: str,
        player_id: str,
        avatar: dict[str, Any],
        lease_token: str,
    ) -> bool:
        if self.redis is None:
            return True
        ttl = self.presence_ttl_seconds
        result = await self.redis.eval(
            self._REFRESH_SCRIPT,
            3,
            self._owner_key(instance_id, player_id),
            self._presence_key(instance_id),
            self._avatar_key(instance_id, player_id),
            lease_token,
            time.time() + ttl,
            player_id,
            ttl,
            json.dumps(avatar, separators=(",", ":")),
        )
        return bool(result)

    async def is_owner(
        self, instance_id: str, player_id: str, lease_token: str
    ) -> bool:
        if self.redis is None:
            async with self.lock:
                current = self.connections.get((instance_id, player_id))
                return current is not None and current.lease_token == lease_token
        owner = await self.redis.get(self._owner_key(instance_id, player_id))
        return owner == lease_token

    async def touch_presence(self, instance_id: str, player_id: str) -> bool:
        async with self.lock:
            connection = self.connections.get((instance_id, player_id))
            avatar = self.avatars.get((instance_id, player_id))
            if connection is None or avatar is None:
                return False
            token = connection.lease_token
            snapshot = avatar.copy()
        return await self._refresh_presence(instance_id, player_id, snapshot, token)

    async def _presence_snapshot(
        self, instance_id: str, exclude_player_id: str
    ) -> list[dict[str, Any]]:
        if self.redis is None:
            async with self.lock:
                return [
                    value.copy()
                    for (current_instance, current_player), value in self.avatars.items()
                    if current_instance == instance_id and current_player != exclude_player_id
                ]

        presence_key = self._presence_key(instance_id)
        now = time.time()
        await self.redis.zremrangebyscore(presence_key, "-inf", now)
        player_ids = await self.redis.zrange(presence_key, 0, -1)
        player_ids = [player_id for player_id in player_ids if player_id != exclude_player_id]
        if not player_ids:
            return []
        raw_avatars = await self.redis.mget(
            [self._avatar_key(instance_id, player_id) for player_id in player_ids]
        )
        snapshot = []
        for raw in raw_avatars:
            if raw is None:
                continue
            try:
                value = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                snapshot.append(value)
        return snapshot

    async def _broadcast_local(
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

    async def _publish_event(
        self, instance_id: str, sender_id: str, command: str, payload: dict[str, Any]
    ) -> None:
        if self.redis is None:
            return
        event = {
            "origin": self.node_id,
            "sender_id": sender_id,
            "command": command,
            "payload": payload,
        }
        await self.redis.publish(
            f"map:events:{instance_id}",
            json.dumps(event, separators=(",", ":")),
        )

    async def _listen_for_remote_events(self) -> None:
        if self.pubsub is None:
            return
        async for message in self.pubsub.listen():
            if message.get("type") != "pmessage":
                continue
            try:
                event = json.loads(message["data"])
                if event.get("origin") == self.node_id:
                    continue
                channel = message["channel"]
                instance_id = channel.removeprefix("map:events:")
                await self._broadcast_local(
                    instance_id,
                    event["sender_id"],
                    event["command"],
                    event["payload"],
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue

    async def broadcast(
        self, instance_id: str, sender_id: str, command: str, payload: dict[str, Any]
    ) -> None:
        await self._broadcast_local(instance_id, sender_id, command, payload)
        await self._publish_event(instance_id, sender_id, command, payload)

    async def attach(
        self,
        websocket: WebSocket,
        instance_id: str,
        player_id: str,
        avatar: dict[str, Any],
    ) -> str:
        key = (instance_id, player_id)
        lease_token = uuid4().hex
        async with self.lock:
            old = self.connections.get(key)
            self.connections[key] = Connection(
                websocket,
                instance_id,
                player_id,
                lease_token,
                server_seq=websocket.scope.setdefault("state", {}).get("server_seq", 0),
            )
            self.avatars[key] = avatar.copy()
        if old is not None and old.websocket is not websocket:
            try:
                await old.websocket.close(code=4001)
            except Exception:
                pass

        await self._store_presence(instance_id, player_id, avatar, lease_token)
        snapshot = await self._presence_snapshot(instance_id, player_id)
        connection = self.connections[key]
        await self._send(connection, "ENTER", {"instance_id": instance_id, "players": snapshot})
        await self.broadcast(instance_id, player_id, "ENTER", {"player": avatar})
        return lease_token

    async def detach(self, websocket: WebSocket, instance_id: str, player_id: str) -> bool:
        key = (instance_id, player_id)
        async with self.lock:
            current = self.connections.get(key)
            if current is None or current.websocket is not websocket:
                return False
            self.connections.pop(key, None)
        if self.redis is None:
            return True
        released = await self.redis.eval(
            self._RELEASE_SCRIPT,
            3,
            self._owner_key(instance_id, player_id),
            self._presence_key(instance_id),
            self._avatar_key(instance_id, player_id),
            current.lease_token,
            player_id,
        )
        if not released:
            async with self.lock:
                self.avatars.pop(key, None)
        return bool(released)

    async def update_avatar(
        self, instance_id: str, player_id: str, values: dict[str, Any]
    ) -> None:
        key = (instance_id, player_id)
        async with self.lock:
            avatar = self.avatars.get(key)
            connection = self.connections.get(key)
            if avatar is None or connection is None:
                return
            avatar.update(values)
            payload = avatar.copy()
            token = connection.lease_token
        if not await self._refresh_presence(instance_id, player_id, payload, token):
            return
        await self.broadcast(instance_id, player_id, "MOVE_SYNC", {"player": payload})

    async def avatar(self, instance_id: str, player_id: str) -> dict[str, Any] | None:
        async with self.lock:
            value = self.avatars.get((instance_id, player_id))
            return value.copy() if value else None

    async def _delete_presence(
        self, instance_id: str, player_id: str, lease_token: str
    ) -> bool:
        if self.redis is None:
            return True
        return bool(
            await self.redis.eval(
                self._RELEASE_SCRIPT,
                3,
                self._owner_key(instance_id, player_id),
                self._presence_key(instance_id),
                self._avatar_key(instance_id, player_id),
                lease_token,
                player_id,
            )
        )

    async def remove_avatar(self, instance_id: str, player_id: str) -> None:
        key = (instance_id, player_id)
        async with self.lock:
            connection = self.connections.pop(key, None)
            existed = self.avatars.pop(key, None) is not None
        if connection is None:
            return
        released = await self._delete_presence(
            instance_id, player_id, connection.lease_token
        )
        if existed and released:
            await self.broadcast(instance_id, player_id, "LEAVE", {"player_id": player_id})

    async def evict_player(self, instance_id: str, player_id: str) -> None:
        key = (instance_id, player_id)
        async with self.lock:
            connection = self.connections.pop(key, None)
            existed = self.avatars.pop(key, None) is not None
        if connection is None:
            return
        try:
            await connection.websocket.close(code=4002, reason="Entered personal level")
        except Exception:
            pass
        released = await self._delete_presence(
            instance_id, player_id, connection.lease_token
        )
        if existed and released:
            await self.broadcast(instance_id, player_id, "LEAVE", {"player_id": player_id})


map_connections = MapConnectionManager()
