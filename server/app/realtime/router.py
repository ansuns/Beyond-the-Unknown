import asyncio
import logging
import math
from collections import deque
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.security import decode_access_token
from app.modules.maps.repository import (
    expire_disconnected_membership,
    get_membership,
    mark_disconnected,
    persist_position,
    remove_membership,
    touch_membership,
)
from app.realtime.manager import map_connections

router = APIRouter()
logger = logging.getLogger(__name__)
DIRECTIONS = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"}
ACTION_IDS = {"ACT_001", "ACT_002", "ACT_003", "ACT_004"}


async def _send(websocket: WebSocket, command: str, payload: dict) -> None:
    state = websocket.scope.setdefault("state", {})
    seq = state.get("server_seq", 0) + 1
    state["server_seq"] = seq
    await websocket.send_json(map_connections.message(command, payload, seq))


async def _expire_after_grace(
    player_id: UUID, session_id: UUID, disconnected_at: datetime, grace: int
) -> None:
    await asyncio.sleep(grace)
    async with SessionFactory() as session:
        removed_instance = await expire_disconnected_membership(
            session, player_id, session_id, disconnected_at
        )
    if removed_instance is not None:
        await map_connections.remove_avatar(str(removed_instance), str(player_id))


async def _mark_disconnected(
    player_id: UUID, session_id: UUID, grace: int
) -> None:
    disconnected_at = datetime.now(UTC)
    async with SessionFactory() as session:
        await mark_disconnected(session, player_id, session_id, disconnected_at)
    asyncio.create_task(
        _expire_after_grace(player_id, session_id, disconnected_at, grace)
    )


@router.websocket("/ws/map")
async def map_websocket(websocket: WebSocket) -> None:
    settings = get_settings()
    await websocket.accept()
    player_id = None
    instance_id = None
    session_id = None
    joined = False
    try:
        auth_message = await websocket.receive_json()
        auth_payload = auth_message.get("payload", {}) if isinstance(auth_message, dict) else {}
        if (
            not isinstance(auth_message, dict)
            or auth_message.get("v") != 1
            or auth_message.get("cmd") != "AUTH"
            or auth_message.get("seq") != 0
            or not isinstance(auth_payload, dict)
        ):
            await _send(websocket, "AUTH_FAIL", {"reason": "AUTH must be the first message"})
            await websocket.close(code=4401)
            return
        try:
            player_id = decode_access_token(auth_payload.get("token", ""), settings.jwt_secret)
        except ValueError:
            await _send(websocket, "AUTH_FAIL", {"reason": "Invalid access token"})
            await websocket.close(code=4401)
            return

        async with SessionFactory() as session:
            player = (
                await session.execute(
                    text("""
                        SELECT status::text, current_character_id
                        FROM players WHERE player_id = :player_id
                    """),
                    {"player_id": player_id},
                )
            ).mappings().one_or_none()
        if player is None or player["status"] != "NORMAL":
            await _send(websocket, "AUTH_FAIL", {"reason": "Player account is unavailable"})
            await websocket.close(code=4403)
            return
        await _send(websocket, "AUTH_OK", {"player_id": str(player_id)})

        enter_message = await websocket.receive_json()
        enter_payload = enter_message.get("payload", {}) if isinstance(enter_message, dict) else {}
        if (
            not isinstance(enter_message, dict)
            or enter_message.get("v") != 1
            or enter_message.get("cmd") not in {"ENTER", "RECONNECT"}
            or not isinstance(enter_message.get("seq"), int)
            or isinstance(enter_message.get("seq"), bool)
            or enter_message.get("seq") <= 0
            or not isinstance(enter_payload, dict)
        ):
            await _send(websocket, "ERROR", {"code": "ENTER_REQUIRED"})
            await websocket.close(code=4400)
            return
        try:
            instance_id = UUID(str(enter_payload["instance_id"]))
            session_id = UUID(str(enter_payload["session_id"]))
        except (KeyError, ValueError, TypeError):
            await _send(websocket, "ERROR", {"code": "INVALID_MEMBERSHIP"})
            await websocket.close(code=4400)
            return

        async with SessionFactory() as session:
            membership = await get_membership(session, player_id, instance_id, session_id)
            if (
                membership is None
                or membership["player_status"] != "NORMAL"
                or membership["instance_status"] != "ACTIVE"
            ):
                await _send(websocket, "ERROR", {"code": "MEMBERSHIP_NOT_FOUND"})
                await websocket.close(code=4403)
                return
            age = (datetime.now(UTC) - membership["last_seen_at"]).total_seconds()
            if age > settings.map_reconnect_grace_seconds:
                await _send(websocket, "ERROR", {"code": "RECONNECT_WINDOW_EXPIRED"})
                await websocket.close(code=4408)
                return

        joined = True
        await map_connections.attach(
            websocket,
            str(instance_id),
            str(player_id),
            {
                "player_id": str(player_id),
                "character_id": membership["current_character_id"],
                "x": float(membership["position_x"]),
                "y": float(membership["position_y"]),
                "direction": membership["direction"],
            },
        )
        async with SessionFactory() as session:
            await touch_membership(session, player_id, session_id)
        last_seq = int(enter_message.get("seq", 0))
        last_move_at = asyncio.get_running_loop().time()
        action_times: deque[float] = deque()

        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict) or message.get("v") != 1:
                await _send(websocket, "ERROR", {"code": "INVALID_MESSAGE"})
                continue
            seq = message.get("seq")
            if not isinstance(seq, int) or isinstance(seq, bool) or seq <= last_seq:
                continue
            last_seq = seq
            command = message.get("cmd")
            payload = message.get("payload", {})
            if not isinstance(payload, dict):
                await _send(websocket, "ERROR", {"code": "INVALID_PAYLOAD"})
                continue

            if command == "PING":
                async with SessionFactory() as session:
                    await touch_membership(session, player_id, session_id)
                await _send(
                    websocket,
                    "PONG",
                    {"server_ts": int(datetime.now(UTC).timestamp() * 1000)},
                )
            elif command == "MOVE_SYNC":
                try:
                    if (
                        not isinstance(payload["client_tick"], int)
                        or isinstance(payload["client_tick"], bool)
                        or payload["client_tick"] < 0
                    ):
                        raise ValueError
                    if isinstance(payload["x"], bool) or isinstance(payload["y"], bool):
                        raise ValueError
                    x, y = float(payload["x"]), float(payload["y"])
                    direction = payload["dir"]
                    if not math.isfinite(x) or not math.isfinite(y) or direction not in DIRECTIONS:
                        raise ValueError
                except (KeyError, TypeError, ValueError):
                    await _send(websocket, "ERROR", {"code": "INVALID_MOVE"})
                    continue
                now = asyncio.get_running_loop().time()
                interval = 1.0 / max(settings.map_move_rate_hz, 1.0)
                if now - last_move_at < interval:
                    continue
                avatar = await map_connections.avatar(str(instance_id), str(player_id))
                if avatar is None:
                    break
                elapsed = max(now - last_move_at, 0.1) if last_move_at else 1.0
                if (
                    math.dist((x, y), (avatar["x"], avatar["y"]))
                    > settings.map_max_speed * elapsed + 2.0
                ):
                    await _send(websocket, "ERROR", {"code": "MOVE_TOO_FAST"})
                    continue
                async with SessionFactory() as session:
                    saved = await persist_position(
                        session, player_id, session_id, x, y, direction
                    )
                if not saved:
                    await _send(websocket, "ERROR", {"code": "MEMBERSHIP_NOT_FOUND"})
                    break
                last_move_at = now
                await map_connections.update_avatar(
                    str(instance_id),
                    str(player_id),
                    {"x": x, "y": y, "direction": direction},
                )
            elif command == "ACTION_BROADCAST":
                action_id = payload.get("action_id")
                if not isinstance(action_id, str) or action_id not in ACTION_IDS:
                    await _send(websocket, "ERROR", {"code": "ACTION_NOT_ALLOWED"})
                    continue
                now = asyncio.get_running_loop().time()
                while action_times and now - action_times[0] > settings.map_action_window_seconds:
                    action_times.popleft()
                if len(action_times) >= settings.map_action_rate_limit:
                    await _send(websocket, "ERROR", {"code": "ACTION_RATE_LIMITED"})
                    continue
                action_times.append(now)
                await map_connections.broadcast(
                    str(instance_id),
                    str(player_id),
                    "ACTION_BROADCAST",
                    {"player_id": str(player_id), "action_id": action_id},
                )
            elif command == "LEAVE":
                async with SessionFactory() as session:
                    await remove_membership(session, player_id, session_id)
                await map_connections.remove_avatar(str(instance_id), str(player_id))
                await _send(websocket, "LEAVE", {"success": True})
                joined = False
                await websocket.close(code=1000)
                break
            else:
                await _send(websocket, "ERROR", {"code": "COMMAND_NOT_ALLOWED"})
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Map WebSocket handler failed")
        try:
            await _send(websocket, "ERROR", {"code": "INTERNAL_ERROR"})
        except Exception:
            pass
    finally:
        if joined and player_id is not None and instance_id is not None and session_id is not None:
            is_current = await map_connections.detach(
                websocket, str(instance_id), str(player_id)
            )
            if is_current:
                await _mark_disconnected(
                    player_id, session_id, settings.map_reconnect_grace_seconds
                )
