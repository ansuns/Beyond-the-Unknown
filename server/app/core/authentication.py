from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import decode_access_token

_bearer = HTTPBearer(auto_error=False)


async def get_current_player_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    session: AsyncSession = Depends(get_session),
) -> UUID:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    try:
        player_id = decode_access_token(credentials.credentials, settings.jwt_secret)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from exc

    player_status = (
        await session.execute(
            text("SELECT status::text FROM players WHERE player_id = :player_id"),
            {"player_id": player_id},
        )
    ).scalar_one_or_none()
    if player_status is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Player no longer exists",
        )
    if player_status != "NORMAL":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Player account is unavailable",
        )
    return player_id
