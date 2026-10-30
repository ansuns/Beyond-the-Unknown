from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.database import get_session
from app.modules.progression.schemas import ClaimRewardRequest, SettleLevelRequest
from app.modules.progression.repository import (
    ObjectivesIncomplete,
    ProgressionRunNotActive,
    ProgressionRunNotFound,
    RewardNotClaimable,
    RewardNotFound,
    get_leaderboard,
    get_player_collections,
    get_player_discoveries,
    get_world_archive,
    get_progress_summary,
    list_player_rewards,
    claim_reward,
    settle_level,
)
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.post("/level/settle")
async def post_level_settle(
    payload: SettleLevelRequest,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await settle_level(session, player_id, payload.run_id, idempotency_key)
        await session.commit()
    except ProgressionRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Level run not found") from exc
    except ProgressionRunNotActive as exc:
        raise HTTPException(status_code=409, detail="Level run is not settleable") from exc
    except ObjectivesIncomplete as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "OBJECTIVES_INCOMPLETE", "missing_objectives": exc.missing},
        ) from exc
    return success_envelope(data, request.state.request_id)



@router.get("/discovery/me")
async def get_my_discoveries(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_player_discoveries(session, player_id)
    return success_envelope({"discoveries": data}, request.state.request_id)


@router.get("/collection/me")
async def get_my_collections(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_player_collections(session, player_id)
    return success_envelope({"collections": data}, request.state.request_id)


@router.get("/archive")
async def get_world_archive_endpoint(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_world_archive(session, limit)
    return success_envelope({"entries": data}, request.state.request_id)


@router.get("/progress/me")
async def get_my_progress(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_progress_summary(session, player_id)
    return success_envelope(data, request.state.request_id)


@router.get("/leaderboard")
async def get_leaderboard_endpoint(
    request: Request,
    board_type: Annotated[str, Query(pattern="^(EXPLORE|CLEAR|COLLECT)$")] = "EXPLORE",
    season_type: Annotated[str, Query(pattern="^(WEEKLY|MONTHLY)$")] = "WEEKLY",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await get_leaderboard(session, player_id, board_type, season_type, limit)
    await session.commit()
    return success_envelope(data, request.state.request_id)


@router.get("/reward/me")
async def get_my_rewards(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await list_player_rewards(session, player_id)
    return success_envelope({"rewards": data}, request.state.request_id)


@router.post("/reward/claim")
async def post_claim_reward(
    payload: ClaimRewardRequest,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await claim_reward(session, player_id, payload.player_reward_id)
    except RewardNotFound as exc:
        raise HTTPException(status_code=404, detail="Reward record not found") from exc
    except RewardNotClaimable as exc:
        raise HTTPException(
            status_code=409, detail="Reward is already claimed or not claimable"
        ) from exc
    await session.commit()
    return success_envelope(data, request.state.request_id)
