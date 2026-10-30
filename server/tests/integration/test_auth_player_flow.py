import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.auth.provider import get_wechat_code_provider

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL and apply Alembic migrations for PostgreSQL integration tests",
)


class FakeWeChatProvider:
    async def exchange(self, code: str) -> str:
        return f"test-openid-{code}"


def test_login_is_idempotent_and_player_character_data_is_owned() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            payload = {"wx_code": f"code-{uuid4()}", "request_id": "integration-login-1"}
            first = client.post("/api/v1/auth/login", json=payload)
            second = client.post("/api/v1/auth/login", json=payload)
            assert first.status_code == second.status_code == 200
            first_data, second_data = first.json()["data"], second.json()["data"]
            assert first_data["is_new_player"] is True
            assert second_data["is_new_player"] is False
            assert first_data["player_id"] == second_data["player_id"]
            assert "session_key" not in first.text

            headers = {"Authorization": f"Bearer {first_data['access_token']}"}
            me = client.get("/api/v1/player/me", headers=headers)
            assert me.status_code == 200
            assert me.json()["data"]["player_id"] == first_data["player_id"]

            roles = client.get("/api/v1/player/characters", headers=headers)
            assert roles.status_code == 200
            items = roles.json()["data"]["characters"]
            assert len(items) == 12
            assert all(item["is_unlocked"] for item in items)

            selected = client.put(
                "/api/v1/player/character", headers=headers, json={"character_id": "CHR_001"}
            )
            assert selected.status_code == 200
            assert selected.json()["data"]["current_character_id"] == "CHR_001"

            invalid = client.put(
                "/api/v1/player/character", headers=headers, json={"character_id": "CHR_999"}
            )
            assert invalid.status_code == 404
            unauthorized = client.get(
                "/api/v1/player/me", headers={"Authorization": "Bearer invalid-token"}
            )
            assert unauthorized.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_concurrent_first_login_creates_one_player() -> None:
    import asyncio

    from app.core.config import get_settings
    from app.core.database import SessionFactory
    from app.modules.auth.service import login_with_wechat

    class SameIdentityProvider:
        async def exchange(self, code: str) -> str:
            return f"concurrent-openid-{code}"

    code = str(uuid4())
    settings = get_settings()

    async def login_once():
        async with SessionFactory() as session:
            return await login_with_wechat(session, SameIdentityProvider(), settings, code)

    results = await asyncio.gather(login_once(), login_once())
    assert len({result["player_id"] for result in results}) == 1
    assert sum(result["is_new_player"] for result in results) == 1
