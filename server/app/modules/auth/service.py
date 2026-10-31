from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import create_access_token, hash_wechat_openid
from app.modules.auth.provider import WeChatCodeProvider
from app.modules.auth.repository import get_or_create_player
from app.modules.level_events.service import record_login_event


async def login_with_wechat(
    session: AsyncSession, provider: WeChatCodeProvider, settings: Settings, code: str
) -> dict[str, Any]:
    settings.validate_auth_secrets()
    openid = await provider.exchange(code)
    digest = hash_wechat_openid(openid, settings.openid_hmac_secret)
    player, is_new_player = await get_or_create_player(session, digest)
    # Authenticate first, count the login second: a progress-side failure must
    # never stop a player from signing in, so this is best effort by design.
    await record_login_event(session, player["player_id"])
    token = create_access_token(
        player["player_id"], settings.jwt_secret, settings.jwt_access_token_seconds
    )
    return {
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": settings.jwt_access_token_seconds,
        "player_id": str(player["player_id"]),
        "character_id": player["current_character_id"],
        "is_new_player": is_new_player,
        "progress_version": player["progress_version"],
        "server_time": int(datetime.now(UTC).timestamp()),
    }
