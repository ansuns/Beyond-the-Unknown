from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.database import get_session
from app.modules.characters.repository import list_player_characters, select_player_character
from app.modules.players.repository import get_player_profile
from app.modules.players.schemas import SelectCharacterRequest
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.get("/me")
async def get_me(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    profile = await get_player_profile(session, player_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player not found")
    return success_envelope(profile, request.state.request_id)


@router.get("/characters")
async def get_characters(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await list_player_characters(session, player_id)
    return success_envelope(data, request.state.request_id)


@router.put("/character")
async def put_character(
    payload: SelectCharacterRequest,
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    selected = await select_player_character(session, player_id, payload.character_id)
    if selected is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found, disabled, or not unlocked",
        )
    return success_envelope(
        {"success": True, "current_character_id": selected}, request.state.request_id
    )
