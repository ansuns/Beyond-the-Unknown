from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.database import get_session
from app.modules.levels.repository import (
    ActiveLevelRunExists,
    IdempotencyConflict,
    InvalidLevelRunState,
    InvalidLevelPosition,
    update_level_position,
    LevelLocked,
    LevelNotFound,
    PlayerNotInMap,
    abandon_level,
    enter_level,
    list_levels,
    start_level,
)
from app.modules.levels.schemas import (
    LevelEnterRequest,
    LevelPositionRequest,
    LevelRunRequest,
)
from app.realtime.manager import map_connections
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.get("/")
async def get_levels(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await list_levels(session, player_id)
    return success_envelope({"levels": data}, request.state.request_id)


@router.post("/enter")
async def post_enter_level(
    payload: LevelEnterRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await enter_level(
            session,
            player_id,
            payload.level_id,
            payload.entrance_id,
            idempotency_key,
        )
    except LevelNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Level or entrance not found",
        ) from exc
    except LevelLocked as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Level is locked"
        ) from exc
    except PlayerNotInMap as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Player is not in the required map instance",
        ) from exc
    except ActiveLevelRunExists as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Player already has an active level run",
        ) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was used with a different request",
        ) from exc

    if data.get("map_instance_id"):
        await map_connections.evict_player(data["map_instance_id"], str(player_id))
    return success_envelope(data, request.state.request_id)


@router.post("/start")
async def post_start_level(
    payload: LevelRunRequest,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await start_level(session, player_id, payload.run_id)
    except LevelNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    except InvalidLevelRunState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Level run cannot be started from its current state",
        ) from exc
    return success_envelope(data, request.state.request_id)


@router.post("/abandon")
async def post_abandon_level(
    payload: LevelRunRequest,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await abandon_level(session, player_id, payload.run_id)
    except LevelNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    except InvalidLevelRunState as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Completed or failed runs cannot be abandoned",
        ) from exc
    return success_envelope(data, request.state.request_id)


@router.post("/position")
async def post_level_position(
    payload: LevelPositionRequest,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await update_level_position(
            session, player_id, payload.run_id, payload.x, payload.y
        )
    except LevelNotFound as exc:
        raise HTTPException(status_code=404, detail="Level run not found") from exc
    except InvalidLevelRunState as exc:
        raise HTTPException(status_code=409, detail="Level run is not active") from exc
    except InvalidLevelPosition as exc:
        raise HTTPException(
            status_code=422, detail="Position is outside the configured room bounds"
        ) from exc
    return success_envelope(data, request.state.request_id)
