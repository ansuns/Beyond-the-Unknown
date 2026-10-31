import logging
from typing import Protocol

import httpx
from fastapi import Depends

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class InvalidWeChatCode(Exception):
    pass


class WeChatProviderUnavailable(Exception):
    pass


class WeChatCodeProvider(Protocol):
    async def exchange(self, code: str) -> str: ...


class WeChatCodeExchange:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def exchange(self, code: str) -> str:
        if not self.settings.wechat_app_id or not self.settings.wechat_app_secret:
            raise WeChatProviderUnavailable("WeChat login is not configured")
        params = {
            "appid": self.settings.wechat_app_id,
            "secret": self.settings.wechat_app_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.wechat_api_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = await client.get(self.settings.wechat_api_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except (
            httpx.TimeoutException,
            httpx.RequestError,
            httpx.HTTPStatusError,
            ValueError,
        ) as exc:
            raise WeChatProviderUnavailable(
                "WeChat identity service is unavailable"
            ) from exc

        if not isinstance(payload, dict):
            raise WeChatProviderUnavailable("WeChat identity response is malformed")
        error_code = payload.get("errcode")
        if error_code is not None:
            try:
                parsed_error_code = int(error_code)
            except (TypeError, ValueError):
                raise WeChatProviderUnavailable(
                    "WeChat identity service returned an invalid error"
                ) from None
            if parsed_error_code in {40029, 40163}:
                raise InvalidWeChatCode("WeChat login code is invalid or already used")
            raise WeChatProviderUnavailable("WeChat identity service rejected the request")
        openid = payload.get("openid")
        if not isinstance(openid, str) or not openid:
            raise WeChatProviderUnavailable("WeChat identity response is incomplete")
        # session_key is intentionally neither returned nor persisted.
        return openid


class LocalCodeProvider:
    """Maps a browser device code to a stable openid for local development.

    The Cocos web preview has no ``wx.login``, so without this the only way to
    see the client run is inside WeChat DevTools. This provider is not a WeChat
    emulator and must never be mistaken for one: it is refused unless
    ``LOCAL_LOGIN_ENABLED`` is set, and refused outright when ``APP_ENV`` is
    production. Every login it serves is logged at warning level so a deployed
    log would show it immediately.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def exchange(self, code: str) -> str:
        if not self.settings.local_login_allowed():
            raise WeChatProviderUnavailable("Local login is disabled")
        if not isinstance(code, str) or not code.strip():
            raise InvalidWeChatCode("Local login code is empty")
        logger.warning(
            "LOCAL LOGIN in use app_env=%s code_prefix=%s",
            self.settings.app_env,
            code[:16],
        )
        return f"local:{code.strip()}"


def get_wechat_code_provider(
    settings: Settings = Depends(get_settings),
) -> WeChatCodeProvider:
    if settings.app_env != "test" and settings.local_login_allowed():
        return LocalCodeProvider(settings)
    return WeChatCodeExchange(settings)
