"""The local browser login must be opt-in and impossible in production."""

import pytest

from app.core.config import Settings
from app.modules.auth.provider import (
    LocalCodeProvider,
    WeChatCodeExchange,
    WeChatProviderUnavailable,
    get_wechat_code_provider,
)


def test_disabled_by_default() -> None:
    settings = Settings(app_env="local")
    assert settings.local_login_allowed() is False
    assert isinstance(get_wechat_code_provider(settings), WeChatCodeExchange)


def test_enabled_only_when_asked_for() -> None:
    settings = Settings(app_env="local", local_login_enabled=True)
    assert settings.local_login_allowed() is True
    assert isinstance(get_wechat_code_provider(settings), LocalCodeProvider)


@pytest.mark.parametrize("app_env", ["production", "prod", "staging", "PRODUCTION"])
def test_never_allowed_in_deployed_environments(app_env: str) -> None:
    settings = Settings(app_env=app_env, local_login_enabled=True)
    assert settings.local_login_allowed() is False
    assert isinstance(get_wechat_code_provider(settings), WeChatCodeExchange)


def test_test_environment_uses_the_real_wechat_path() -> None:
    """Tests replace the provider with a stub; nothing should be implicit."""
    settings = Settings(app_env="test", local_login_enabled=True)
    assert isinstance(get_wechat_code_provider(settings), WeChatCodeExchange)


def test_provider_refuses_when_the_flag_is_off() -> None:
    provider = LocalCodeProvider(Settings(app_env="local"))
    with pytest.raises(WeChatProviderUnavailable):
        import asyncio

        asyncio.run(provider.exchange("browser-abc"))


def test_provider_maps_codes_to_stable_openids() -> None:
    import asyncio

    provider = LocalCodeProvider(Settings(app_env="local", local_login_enabled=True))
    first = asyncio.run(provider.exchange("browser-abc"))
    second = asyncio.run(provider.exchange("browser-abc"))
    other = asyncio.run(provider.exchange("browser-xyz"))
    assert first == second == "local:browser-abc"
    assert other != first
