from typing import Protocol

import httpx
from fastapi import Depends

from app.core.config import Settings, get_settings


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
                timeout=self.settings.wechat_api_timeout_seconds, transport=self.transport
            ) as client:
                response = await client.get(self.settings.wechat_api_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.TimeoutException, httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
            raise WeChatProviderUnavailable("WeChat identity service is unavailable") from exc

        error_code = payload.get("errcode")
        if error_code is not None:
            if int(error_code) in {40029, 40163}:
                raise InvalidWeChatCode("WeChat login code is invalid or already used")
            raise WeChatProviderUnavailable("WeChat identity service rejected the request")
        openid = payload.get("openid")
        if not isinstance(openid, str) or not openid:
            raise WeChatProviderUnavailable("WeChat identity response is incomplete")
        # session_key is intentionally neither returned nor persisted.
        return openid


def get_wechat_code_provider(
    settings: Settings = Depends(get_settings),
) -> WeChatCodeProvider:
    return WeChatCodeExchange(settings)
