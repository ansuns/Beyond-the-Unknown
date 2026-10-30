from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.modules.auth.provider import (
    InvalidWeChatCode,
    WeChatCodeProvider,
    WeChatProviderUnavailable,
    get_wechat_code_provider,
)
from app.modules.auth.repository import PlayerBannedError
from app.modules.auth.schemas import WeChatLoginRequest
from app.modules.auth.service import login_with_wechat
from app.schemas.envelope import success_envelope

router = APIRouter()


@router.post("/login")
async def wechat_login(
    payload: WeChatLoginRequest,
    session: AsyncSession = Depends(get_session),
    provider: WeChatCodeProvider = Depends(get_wechat_code_provider),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        data = await login_with_wechat(session, provider, settings, payload.wx_code)
    except InvalidWeChatCode as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid WeChat login code") from exc
    except PlayerBannedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Player account is unavailable") from exc
    except (WeChatProviderUnavailable, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Login service unavailable") from exc
    return success_envelope(data, payload.request_id)
