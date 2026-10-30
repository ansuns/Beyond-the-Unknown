from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.database import get_session
from app.modules.levels.repository import (
    ActiveLevelRunExists,
    IdempotencyConflict,
    InvalidLevelRunState,
    LevelLocked,
    LevelNotFound,
    PlayerNotInMap,
    abandon_level,
    enter_level,
    list_levels,
    start_level,
)
from app.modules.gameplay.service import (
    InvalidLawAction,
    LawCooldown,
    LawIdempotencyConflict,
    LevelRunNotFound,
    MechanismNotFound,
    apply_law_action,
    get_run_mechanisms,
)
from app.modules.levels.schemas import (\n    LawActionRequest,\n    LevelEnterRequest,\n    LevelRunRequest,\n)
from app.realtime.manager import map_connections
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.get("/")
async def get_levels(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await list_levels(session)
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


@router.post("/law/action")
async def post_law_action(
    payload: LawActionRequest,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await apply_law_action(
            session,
            player_id,
            payload.run_id,
            payload.rule_id,
            payload.mechanism_id,
            payload.action,
            idempotency_key,
        )
    except LevelRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    except MechanismNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mechanism does not belong to this personal run",
        ) from exc
    except LawIdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was used with a different law action",
        ) from exc
    except LawCooldown as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc
    except InvalidLawAction as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return success_envelope(data, request.state.request_id)


@router.get("/runs/{run_id}/mechanisms")
async def get_personal_run_mechanisms(
    run_id: UUID,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await get_run_mechanisms(session, player_id, run_id)
    except LevelRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    return success_envelope(data, request.state.request_id)
