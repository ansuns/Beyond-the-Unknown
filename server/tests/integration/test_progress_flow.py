# ruff: noqa: I001

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.main import app
from app.modules.auth.provider import get_wechat_code_provider


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="Set TEST_DATABASE_URL and apply Alembic migrations for PostgreSQL integration tests",
)


class FakeWeChatProvider:
    async def exchange(self, code: str) -> str:
        return f"progress-test-openid-{code}"


def _db_exec(statements: list[tuple[str, dict | None]]) -> None:
    async def execute() -> None:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.begin() as connection:
                for statement, parameters in statements:
                    await connection.execute(text(statement), parameters or {})
        finally:
            await engine.dispose()

    asyncio.run(execute())


def _set_test_content(ready: bool) -> None:
    if ready:
        statements = [
            ("""
                UPDATE rule_catalog
                SET cooldown_ms = 5000, radius = 2.0, duration_ms = 1000,
                    lease_timeout_ms = 5000, config_status = 'READY'
            """, None),
            ("""
                UPDATE combo_catalog
                SET time_window_ms = 10000, config_status = 'READY'
            """, None),
            ("""
                UPDATE level_mechanism_catalog
                SET position_x = 0, position_y = 0
                WHERE level_id = 'LV-ROOM-02' AND mechanism_config_id = 'MECH_BRIDGE'
            """, None),
            ("""
                UPDATE score_rule_config
                SET delta = CASE reason
                    WHEN 'EXP_DISCOVER' THEN 5
                    WHEN 'CLEAR_STAGE' THEN 10
                    WHEN 'COLLECT_NEW' THEN 2
                END,
                config_status = 'READY'
            """, None),
            ("""
                INSERT INTO rewards
                    (reward_id, reward_type, reward_name, condition_ref,
                     grant_mode, payload, is_paid, is_enabled)
                VALUES
                    ('TEST-CLAIM-BADGE', 'RT_BADGE', '测试徽章',
                     'TEST-DISCOVERY-CONDITION', 'CLAIM', '{}'::jsonb, false, true)
                ON CONFLICT (reward_id) DO NOTHING
            """, None),
            ("""
                INSERT INTO reward_conditions
                    (condition_id, trigger_type, condition_config,
                     reward_id, is_enabled, config_status)
                VALUES
                    ('TEST-DISCOVERY-CONDITION', 'DISCOVERY',
                     '{"discovery_id":"DISC-COMBO-001"}'::jsonb,
                     'TEST-CLAIM-BADGE', true, 'READY')
                ON CONFLICT (condition_id) DO NOTHING
            """, None),
        ]
    else:
        statements = [
            ("""
                UPDATE rule_catalog
                SET cooldown_ms = NULL, radius = NULL, duration_ms = NULL,
                    lease_timeout_ms = NULL, config_status = 'TUNING_REQUIRED'
            """, None),
            ("""
                UPDATE combo_catalog
                SET time_window_ms = NULL, config_status = 'TUNING_REQUIRED'
            """, None),
            ("""
                UPDATE level_mechanism_catalog
                SET position_x = NULL, position_y = NULL
            """, None),
            ("""
                UPDATE score_rule_config
                SET delta = NULL, config_status = 'TUNING_REQUIRED'
            """, None),
            ("""
                DELETE FROM player_rewards
                WHERE reward_id = 'TEST-CLAIM-BADGE'
            """, None),
            ("""
                DELETE FROM reward_conditions
                WHERE condition_id = 'TEST-DISCOVERY-CONDITION'
            """, None),
            ("""
                DELETE FROM rewards WHERE reward_id = 'TEST-CLAIM-BADGE'
            """, None),
        ]
    _db_exec(statements)


def _login(client: TestClient) -> dict:
    response = client.post(
        "/api/v1/auth/login",
        json={"wx_code": str(uuid4()), "request_id": "progress-test-login"},
    )
    assert response.status_code == 200
    headers = {
        "Authorization": f"Bearer {response.json()['data']['access_token']}"
    }
    entered = client.post("/api/v1/map/enter", headers=headers)
    assert entered.status_code == 200
    return headers


def test_discovery_world_archive_rewards_settlement_and_leaderboard() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            headers = _login(client)
            entered = client.post(
                "/api/v1/level/enter",
                headers={**headers, "Idempotency-Key": "progress-enter-room2-01"},
                json={"level_id": "LV-ROOM-02", "entrance_id": "ENT-ROOM-02"},
            )
            assert entered.status_code == 200
            run_id = entered.json()["data"]["run_id"]
            started = client.post(
                "/api/v1/level/start",
                headers=headers,
                json={"run_id": run_id},
            )
            assert started.status_code == 200

            _set_test_content(True)
            echo = client.post(
                "/api/v1/level/rule/cast",
                headers={**headers, "Idempotency-Key": "progress-echo-room2-01"},
                json={
                    "run_id": run_id,
                    "rule_id": "RULE_ECHO",
                    "target_id": "MECH_BRIDGE",
                    "target_point": {"x": 0, "y": 0},
                },
            )
            assert echo.status_code == 200, echo.text
            gaze = client.post(
                "/api/v1/level/rule/cast",
                headers={**headers, "Idempotency-Key": "progress-gaze-room2-01"},
                json={
                    "run_id": run_id,
                    "rule_id": "RULE_GAZE",
                    "target_id": "MECH_BRIDGE",
                },
            )
            assert gaze.status_code == 200, gaze.text
            assert gaze.json()["data"]["combo"]["combo_id"] == "COMBO-001"

            discoveries = client.get("/api/v1/player/discoveries", headers=headers)
            discovery_ids = {
                item["discovery_id"] for item in discoveries.json()["data"]["discoveries"]
            }
            assert {"DISC-RULE-ECHO", "DISC-RULE-GAZE", "DISC-COMBO-001"} <= discovery_ids

            collections = client.get("/api/v1/player/collections", headers=headers)
            collection_ids = {
                item["collection_id"] for item in collections.json()["data"]["collections"]
            }
            assert {"COLL-RULE-ECHO", "COLL-RULE-GAZE", "COLL-COMBO-001"} <= collection_ids

            archive = client.get("/api/v1/world/archive", headers=headers)
            archive_ids = {
                item["discovery_id"] for item in archive.json()["data"]["records"]
            }
            assert {"DISC-RULE-ECHO", "DISC-RULE-GAZE", "DISC-COMBO-001"} <= archive_ids

            inbox = client.get("/api/v1/reward", headers=headers)
            pending = inbox.json()["data"]["pending"]
            claimable = next(
                item for item in pending if item["reward_id"] == "TEST-CLAIM-BADGE"
            )
            claim = client.post(
                "/api/v1/reward/claim",
                headers=headers,
                json={"player_reward_id": claimable["player_reward_id"]},
            )
            assert claim.status_code == 200
            assert claim.json()["data"]["status"] == "OWNED"
            repeated_claim = client.post(
                "/api/v1/reward/claim",
                headers=headers,
                json={"player_reward_id": claimable["player_reward_id"]},
            )
            assert repeated_claim.status_code == 200
            assert repeated_claim.json()["data"]["already_claimed"] is True

            settled = client.post(
                "/api/v1/level/settle",
                headers={**headers, "Idempotency-Key": "progress-settle-room2-01"},
                json={"run_id": run_id, "completion_score": 999999},
            )
            assert settled.status_code == 200, settled.text
            result_id = settled.json()["data"]["result_id"]
            assert settled.json()["data"]["result_status"] == "COMPLETED"
            assert "completion_score" not in settled.json()["data"]["score_payload"]

            replay = client.post(
                "/api/v1/level/settle",
                headers={**headers, "Idempotency-Key": "progress-settle-room2-retry"},
                json={"run_id": run_id},
            )
            assert replay.status_code == 200
            assert replay.json()["data"]["result_id"] == result_id
            assert replay.json()["data"]["idempotent_replay"] is True

            progress = client.get("/api/v1/player/progress", headers=headers)
            assert "LV-ROOM-02" in progress.json()["data"]["completed_level_ids"]
            assert progress.json()["data"]["progress_version"] > 0

            explore = client.get(
                "/api/v1/leaderboard?board_type=EXPLORE&period_type=WEEKLY",
                headers=headers,
            )
            assert explore.status_code == 200
            assert explore.json()["data"]["entries"][0]["score"] == 20

            collect = client.get(
                "/api/v1/leaderboard?board_type=COLLECT&period_type=WEEKLY",
                headers=headers,
            )
            assert collect.status_code == 200
            assert collect.json()["data"]["entries"][0]["score"] == 6

            clear = client.get(
                "/api/v1/leaderboard?board_type=CLEAR&period_type=WEEKLY",
                headers=headers,
            )
            assert clear.status_code == 200
            assert clear.json()["data"]["entries"][0]["score"] == 10

            locked = client.post(
                "/api/v1/level/enter",
                headers={**headers, "Idempotency-Key": "progress-hidden-locked-01"},
                json={"level_id": "LV-HIDDEN-01", "entrance_id": "ENT-HIDDEN-01"},
            )
            assert locked.status_code == 403
    finally:
        _set_test_content(False)
        app.dependency_overrides.clear()
