from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authentication import get_current_player_id
from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.modules.maps.repository import MapConfigurationError, enter_main_map
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.post("/enter")
async def enter_map(
    request: Request,
    player_id=Depends(get_current_player_id),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        data, _ = await enter_main_map(
            session,
            player_id,
            settings.map_instance_max_players,
            settings.map_reconnect_grace_seconds,
        )
    except MapConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Main map is temporarily unavailable",
        ) from exc
    return success_envelope(data, request.state.request_id)
