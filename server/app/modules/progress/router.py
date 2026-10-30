from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.database import get_session
from app.modules.progress.repository import (
    IncompleteObjectives,
    RewardNotClaimable,
    RewardNotFound,
    SettlementConfigIncomplete,
    SettlementIdempotencyConflict,
    SettlementRunNotFound,
    SettlementStateConflict,
    claim_reward,
    get_leaderboard,
    get_player_progress,
    list_player_collections,
    list_player_discoveries,
    list_player_rewards,
    list_world_archive,
    settle_level,
)
from app.modules.progress.schemas import LevelSettleRequest, RewardClaimRequest
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.post("/level/settle")
async def post_level_settle(
    payload: LevelSettleRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=200),
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await settle_level(session, player_id, payload.run_id, idempotency_key)
    except SettlementRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Level run not found") from exc
    except SettlementStateConflict as exc:
        raise HTTPException(status_code=409, detail="Level run cannot be settled") from exc
    except SettlementConfigIncomplete as exc:
        raise HTTPException(status_code=503, detail="Objective configuration incomplete") from exc
    except IncompleteObjectives as exc:
        raise HTTPException(status_code=409, detail={"code": "OBJECTIVES_INCOMPLETE", "objective_ids": exc.objective_ids}) from exc
    except SettlementIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
    return success_envelope(data, request.state.request_id)


@router.get("/player/progress")
async def get_progress(request: Request, player_id=Depends(get_current_player_id), session: AsyncSession = Depends(get_session)) -> dict:
    return success_envelope(await get_player_progress(session, player_id), request.state.request_id)


@router.get("/player/discoveries")
async def get_discoveries(request: Request, player_id=Depends(get_current_player_id), session: AsyncSession = Depends(get_session)) -> dict:
    data = await list_player_discoveries(session, player_id)
    return success_envelope({"discoveries": data}, request.state.request_id)


@router.get("/player/collections")
async def get_collections(request: Request, player_id=Depends(get_current_player_id), session: AsyncSession = Depends(get_session)) -> dict:
    data = await list_player_collections(session, player_id)
    return success_envelope({"collections": data}, request.state.request_id)


@router.get("/world/archive")
async def get_archive(request: Request, limit: int = Query(default=50, ge=1, le=100), player_id=Depends(get_current_player_id), session: AsyncSession = Depends(get_session)) -> dict:
    data = await list_world_archive(session, limit)
    return success_envelope({"records": data}, request.state.request_id)


@router.get("/reward")
async def get_rewards(request: Request, player_id=Depends(get_current_player_id), session: AsyncSession = Depends(get_session)) -> dict:
    data = await list_player_rewards(session, player_id)
    pending = [item for item in data if item["status"] == "PENDING_CLAIM"]
    owned = [item for item in data if item["status"] == "OWNED"]
    return success_envelope({"pending": pending, "owned": owned}, request.state.request_id)


@router.post("/reward/claim")
async def post_reward_claim(payload: RewardClaimRequest, request: Request, player_id=Depends(get_current_player_id), session: AsyncSession = Depends(get_session)) -> dict:
    try:
        data = await claim_reward(session, player_id, payload.player_reward_id)
    except RewardNotFound as exc:
        raise HTTPException(status_code=404, detail="Reward not found") from exc
    except RewardNotClaimable as exc:
        raise HTTPException(status_code=409, detail="Reward is not claimable") from exc
    return success_envelope(data, request.state.request_id)


@router.get("/leaderboard")
async def get_leaderboard_endpoint(request: Request, board_type: Literal["EXPLORE", "CLEAR", "COLLECT"] = "EXPLORE", period_type: Literal["WEEKLY", "MONTHLY"] = "WEEKLY", scope: Literal["TOP", "AROUND", "SELF"] = "TOP", limit: int = Query(default=20, ge=1, le=50), player_id=Depends(get_current_player_id), session: AsyncSession = Depends(get_session)) -> dict:
    data = await get_leaderboard(session, player_id, board_type, period_type, scope, limit)
    return success_envelope(data, request.state.request_id)
