import httpx
import pytest

from app.core.config import Settings
from app.modules.auth.provider import InvalidWeChatCode, WeChatCodeExchange


@pytest.mark.asyncio
async def test_wechat_exchange_returns_openid_without_session_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["js_code"] == "temporary-code"
        return httpx.Response(200, json={"openid": "openid-value", "session_key": "must-not-escape"})

    settings = Settings(
        wechat_app_id="test-app", wechat_app_secret="test-secret",
        jwt_secret="j" * 40, openid_hmac_secret="h" * 40,
    )
    provider = WeChatCodeExchange(settings, transport=httpx.MockTransport(handler))
    assert await provider.exchange("temporary-code") == "openid-value"


@pytest.mark.asyncio
async def test_invalid_wechat_code_is_rejected() -> None:
    settings = Settings(
        wechat_app_id="test-app", wechat_app_secret="test-secret",
        jwt_secret="j" * 40, openid_hmac_secret="h" * 40,
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"errcode": 40029, "errmsg": "invalid code"})
    )
    provider = WeChatCodeExchange(settings, transport=transport)
    with pytest.raises(InvalidWeChatCode):
        await provider.exchange("bad-code")
