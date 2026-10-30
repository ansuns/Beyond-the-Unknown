from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.database import get_session
from app.modules.rules.repository import (
    RuleConfigurationIncomplete,
    RuleCoolingDown,
    RuleIdempotencyConflict,
    RuleNotFound,
    RuleNotUnlocked,
    RuleRunNotFound,
    RuleStateConflict,
    RuleTargetInvalid,
    cast_rule,
    get_level_state,
    interact_mechanism,
    list_player_rules,
    maintain_gaze,
    stop_gaze,
)
from app.modules.rules.schemas import (
    RuleCastRequest,
    RuleMaintainRequest,
    MechanismInteractRequest,
    RuleRunRequest,
)
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.get("/rules")
async def get_player_rules(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    rules = await list_player_rules(session, player_id)
    return success_envelope({"rules": rules}, request.state.request_id)


@router.post("/rule/cast")
async def post_rule_cast(
    payload: RuleCastRequest,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    point = payload.target_point.model_dump() if payload.target_point else None
    try:
        data = await cast_rule(
            session,
            player_id,
            payload.run_id,
            payload.rule_id,
            payload.target_id,
            point,
            idempotency_key,
        )
    except RuleRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    except RuleNotUnlocked as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Rule is not unlocked"
        ) from exc
    except RuleNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found"
        ) from exc
    except RuleConfigurationIncomplete as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rule tuning or target configuration is incomplete",
        ) from exc
    except RuleCoolingDown as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "RULE_COOLDOWN",
                "remaining_ms": exc.remaining_ms,
            },
        ) from exc
    except RuleTargetInvalid as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Rule target is invalid or outside the configured scope",
        ) from exc
    except RuleIdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was reused with a different rule request",
        ) from exc
    except RuleStateConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rule cannot be cast in the current level state",
        ) from exc
    return success_envelope(data, request.state.request_id)


@router.post("/rule/stop")
async def post_rule_stop(
    payload: RuleRunRequest,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await stop_gaze(session, player_id, payload.run_id)
    except RuleRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    except RuleStateConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rule cannot be stopped in the current level state",
        ) from exc
    return success_envelope(data, request.state.request_id)


@router.post("/rule/maintain")
async def post_rule_maintain(
    payload: RuleMaintainRequest,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await maintain_gaze(
            session, player_id, payload.run_id, payload.target_id
        )
    except RuleRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    except RuleStateConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No matching active gaze effect",
        ) from exc
    return success_envelope(data, request.state.request_id)


@router.get("/state/{run_id}")
async def get_level_state_endpoint(
    run_id: UUID,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await get_level_state(session, player_id, run_id)
    except RuleRunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level run not found"
        ) from exc
    except RuleStateConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Level run is not active",
        ) from exc
    return success_envelope(data, request.state.request_id)


@router.post("/mechanism/interact")
async def post_mechanism_interact(
    payload: MechanismInteractRequest,
    request: Request,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    try:
        data = await interact_mechanism(
            session,
            player_id,
            payload.run_id,
            payload.mechanism_id,
            idempotency_key,
        )
    except RuleRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Level run not found") from exc
    except RuleTargetInvalid as exc:
        raise HTTPException(
            status_code=422,
            detail="Mechanism is not interactable from the current position",
        ) from exc
    except RuleStateConflict as exc:
        raise HTTPException(
            status_code=409,
            detail="Mechanism prerequisites are not satisfied",
        ) from exc
    except RuleIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail="Idempotency key conflict") from exc
    return success_envelope(data, request.state.request_id)
