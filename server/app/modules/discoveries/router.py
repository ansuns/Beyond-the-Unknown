from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.database import get_session
from app.modules.discoveries.repository import (
    get_exploration_summary,
    list_player_collections,
    list_player_discoveries,
    list_world_archive,
)
from app.schemas.envelope import success_envelope

player_router = APIRouter()
world_router = APIRouter()


@player_router.get("/discoveries")
async def get_discoveries(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await list_player_discoveries(session, player_id, limit, offset)
    return success_envelope(data, request.state.request_id)


@player_router.get("/collections")
async def get_collections(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await list_player_collections(session, player_id)
    return success_envelope(data, request.state.request_id)


@player_router.get("/exploration")
async def get_exploration(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_exploration_summary(session, player_id)
    return success_envelope(data, request.state.request_id)


@world_router.get("/archive")
async def get_world_archive(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    del player_id
    data = await list_world_archive(session, limit, offset)
    return success_envelope(data, request.state.request_id)
