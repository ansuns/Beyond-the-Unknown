# ruff: noqa: I001

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.database import engine
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




def _db_fetch(statement: str, parameters: dict | None = None) -> list[dict]:
    async def fetch() -> list[dict]:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(text(statement), parameters or {})
                return [dict(row._mapping) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(fetch())


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
                WHERE level_id = 'LV-ROOM-02' AND mechanism_config_id = 'M02-BRIDGE-01'
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
                SET position_x = 6.0, position_y = 4.0
                WHERE level_id = 'LV-ROOM-02'
                  AND mechanism_config_id = 'M02-BRIDGE-01'
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
                    "target_id": "M02-BRIDGE-01",
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
                    "target_id": "M02-BRIDGE-01",
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


def _run_outbox_task(envelope: dict) -> None:
    from app.workers.task_worker import _process_outbox_task

    async def execute() -> None:
        await engine.dispose()
        await _process_outbox_task(envelope)
        await engine.dispose()

    asyncio.run(execute())


def test_outbox_finalizes_season_and_grants_rank_reward_once() -> None:
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    season_id = "WEEKLY-19990104"
    reward_id = "TEST-SEASON-BADGE"
    condition_id = "TEST-SEASON-RANK-COND"
    finalize_task_id = str(uuid4())
    try:
        with TestClient(app) as client:
            headers = _login(client)
            profile = client.get("/api/v1/player/me", headers=headers)
            assert profile.status_code == 200
            player_id = profile.json()["data"]["player_id"]

        _db_exec([
            ("""
                INSERT INTO seasons
                    (season_id, season_type, start_at_utc, end_at_utc,
                     status, settlement_status)
                VALUES
                    (:season_id, 'WEEKLY', '1999-01-04T00:00:00Z',
                     '1999-01-11T00:00:00Z', 'ACTIVE', 'PENDING')
                ON CONFLICT (season_id) DO UPDATE
                SET status = 'ACTIVE', settlement_status = 'PENDING',
                    review_until_utc = NULL, reviewed_at_utc = NULL,
                    reviewed_by = NULL, review_note = NULL
            """, {"season_id": season_id}),
            ("""
                INSERT INTO score_events
                    (player_id, board_type, period_id, delta, reason,
                     source_event_id, idempotency_key)
                VALUES
                    (:player_id, 'EXPLORE', :season_id, 100, 'EXP_DISCOVER',
                     'test-season-discovery', 'test-season-score-event')
                ON CONFLICT (board_type, period_id, idempotency_key) DO NOTHING
            """, {"player_id": player_id, "season_id": season_id}),
            ("""
                INSERT INTO rewards
                    (reward_id, reward_type, reward_name, condition_ref,
                     grant_mode, payload, is_paid, is_enabled)
                VALUES
                    (:reward_id, 'RT_BADGE', '赛季第一名徽章',
                     :condition_id, 'CLAIM', '{}'::jsonb, false, true)
                ON CONFLICT (reward_id) DO NOTHING
            """, {"reward_id": reward_id, "condition_id": condition_id}),
            ("""
                INSERT INTO reward_conditions
                    (condition_id, trigger_type, condition_config,
                     reward_id, is_enabled, config_status)
                VALUES
                    (:condition_id, 'SEASON_RANK',
                     jsonb_build_object(
                         'season_type', 'WEEKLY',
                         'board_type', 'EXPLORE',
                         'rank_min', 1,
                         'rank_max', 1
                     ),
                     :reward_id, true, 'READY')
                ON CONFLICT (condition_id) DO UPDATE
                SET condition_config = EXCLUDED.condition_config,
                    is_enabled = true, config_status = 'READY'
            """, {"condition_id": condition_id, "reward_id": reward_id}),
            ("""
                INSERT INTO task_outbox
                    (task_id, task_type, schema_version, payload, idempotency_key)
                VALUES
                    (:task_id, 'season.finalize', 1,
                     jsonb_build_object('season_id', CAST(:season_id AS text)),
                     :idempotency_key)
                ON CONFLICT (idempotency_key) DO NOTHING
            """, {
                "task_id": finalize_task_id,
                "season_id": season_id,
                "idempotency_key": f"season-finalize:{season_id}",
            }),
        ])

        finalize_envelope = {
            "schema_version": 1,
            "task_id": finalize_task_id,
            "task_type": "season.finalize",
            "idempotency_key": f"season-finalize:{season_id}",
            "payload": {"season_id": season_id},
        }
        _run_outbox_task(finalize_envelope)
        review = _db_fetch(
            "SELECT status::text AS status, settlement_status, review_until_utc "
            "FROM seasons WHERE season_id = :season_id",
            {"season_id": season_id},
        )[0]
        assert review["status"] == "SETTLING"
        assert review["settlement_status"] == "REVIEW"

        auto_task = _db_fetch(
            "SELECT task_id, idempotency_key, payload FROM task_outbox "
            "WHERE idempotency_key = :key",
            {"key": f"season-auto-approve:{season_id}"},
        )[0]
        early_envelope = {
            "schema_version": 1,
            "task_id": str(auto_task["task_id"]),
            "task_type": "season.auto_approve",
            "idempotency_key": auto_task["idempotency_key"],
            "payload": auto_task["payload"],
        }
        _run_outbox_task(early_envelope)
        retry_task = _db_fetch(
            "SELECT task_id, idempotency_key, payload FROM task_outbox "
            "WHERE task_type = 'season.auto_approve' AND status = 'PENDING' "
            "AND payload->>'season_id' = :season_id",
            {"season_id": season_id},
        )[0]
        _db_exec([
            ("""
                UPDATE seasons SET review_until_utc = now() - interval '1 second'
                WHERE season_id = :season_id
            """, {"season_id": season_id}),
            ("""
                UPDATE task_outbox
                SET available_at_utc = now() - interval '1 second'
                WHERE task_id = :task_id
            """, {"task_id": retry_task["task_id"]}),
        ])
        approve_envelope = {
            "schema_version": 1,
            "task_id": str(retry_task["task_id"]),
            "task_type": "season.auto_approve",
            "idempotency_key": retry_task["idempotency_key"],
            "payload": retry_task["payload"],
        }
        _run_outbox_task(approve_envelope)
        _run_outbox_task(approve_envelope)

        final = _db_fetch(
            "SELECT status::text AS status, settlement_status, reviewed_by "
            "FROM seasons WHERE season_id = :season_id",
            {"season_id": season_id},
        )[0]
        assert final["status"] == "SETTLED"
        assert final["settlement_status"] == "APPROVED"
        assert final["reviewed_by"] == "AUTO_REVIEW_TIMEOUT"

        grants = _db_fetch(
            "SELECT reward_id, status::text AS status, source "
            "FROM player_rewards WHERE player_id = :player_id AND reward_id = :reward_id",
            {"player_id": player_id, "reward_id": reward_id},
        )
        assert len(grants) == 1
        assert grants[0]["status"] == "PENDING_CLAIM"
        assert grants[0]["source"] == "SEASON"
    finally:
        _db_exec([
            ("""
                DELETE FROM player_rewards
                WHERE reward_id = :reward_id
            """, {"reward_id": reward_id}),
            ("""
                DELETE FROM worker_task_receipts
                WHERE idempotency_key = :finalize_key
                   OR idempotency_key LIKE :approve_pattern
            """, {
                "finalize_key": f"season-finalize:{season_id}",
                "approve_pattern": f"season-auto-approve:{season_id}%",
            }),
            ("""
                DELETE FROM task_outbox
                WHERE payload->>'season_id' = :season_id
            """, {"season_id": season_id}),
            ("""
                DELETE FROM leaderboard_snapshots WHERE season_id = :season_id
            """, {"season_id": season_id}),
            ("""
                DELETE FROM score_events WHERE period_id = :season_id
            """, {"season_id": season_id}),
            ("""
                DELETE FROM seasons WHERE season_id = :season_id
            """, {"season_id": season_id}),
            ("""
                DELETE FROM reward_conditions WHERE condition_id = :condition_id
            """, {"condition_id": condition_id}),
            ("""
                DELETE FROM rewards WHERE reward_id = :reward_id
            """, {"reward_id": reward_id}),
        ])
        app.dependency_overrides.clear()


def test_internal_season_review_requires_key_and_can_reject(monkeypatch) -> None:
    from app.core.config import get_settings

    season_id = "MONTHLY-199901"
    monkeypatch.setattr(get_settings(), "internal_api_key", "test-season-review-key")
    _db_exec([
        ("""
            INSERT INTO seasons
                (season_id, season_type, start_at_utc, end_at_utc,
                 status, settlement_status, review_until_utc)
            VALUES
                (:season_id, 'MONTHLY', '1999-01-01T00:00:00Z',
                 '1999-02-01T00:00:00Z', 'SETTLING', 'REVIEW',
                 now() + interval '10 minutes')
            ON CONFLICT (season_id) DO UPDATE
            SET status = 'SETTLING', settlement_status = 'REVIEW',
                review_until_utc = now() + interval '10 minutes',
                settled_at_utc = NULL, reviewed_at_utc = NULL,
                reviewed_by = NULL, review_note = NULL
        """, {"season_id": season_id}),
    ])
    try:
        with TestClient(app) as client:
            denied = client.post(
                f"/api/v1/internal/seasons/{season_id}/review",
                headers={"X-Internal-API-Key": "wrong-key"},
                json={"decision": "REJECT", "note": "test rejection"},
            )
            assert denied.status_code == 401
            approved_key = client.post(
                f"/api/v1/internal/seasons/{season_id}/review",
                headers={
                    "X-Internal-API-Key": "test-season-review-key",
                    "X-Reviewer-Id": "ci-reviewer",
                },
                json={"decision": "REJECT", "note": "test rejection"},
            )
            assert approved_key.status_code == 200
            assert approved_key.json()["data"]["status"] == "CLOSED"
        row = _db_fetch(
            "SELECT settlement_status, reviewed_by FROM seasons WHERE season_id = :season_id",
            {"season_id": season_id},
        )[0]
        assert row["settlement_status"] == "FAILED"
        assert row["reviewed_by"] == "ci-reviewer"
    finally:
        _db_exec([
            (
                "DELETE FROM actions_log WHERE payload->>'season_id' = :season_id",
                {"season_id": season_id},
            ),
            ("DELETE FROM seasons WHERE season_id = :season_id", {"season_id": season_id}),
        ])


def test_leaderboard_serves_explicit_season_and_rejects_unknown_one() -> None:
    """GDD 13.7 lists season_id as a request field; unknown seasons must not silently
    fall back to the current period."""
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"wx_code": str(uuid4()), "request_id": "lb-season-login"},
            )
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
            assert client.post("/api/v1/map/enter", headers=headers).status_code == 200

            weekly = client.get(
                "/api/v1/leaderboard?board_type=EXPLORE&period_type=WEEKLY",
                headers=headers,
            )
            assert weekly.status_code == 200
            weekly_id = weekly.json()["data"]["season_id"]

            echoed = client.get(
                f"/api/v1/leaderboard?board_type=EXPLORE&season_id={weekly_id}",
                headers=headers,
            )
            assert echoed.status_code == 200
            assert echoed.json()["data"]["season_id"] == weekly_id
            assert echoed.json()["data"]["period_type"] == "WEEKLY"

            monthly = client.get(
                "/api/v1/leaderboard?board_type=EXPLORE&period_type=MONTHLY",
                headers=headers,
            )
            assert monthly.status_code == 200
            monthly_id = monthly.json()["data"]["season_id"]
            assert monthly_id.startswith("MONTHLY-")

            # period_type is derived from the season itself, not from the default value.
            derived = client.get(
                f"/api/v1/leaderboard?board_type=EXPLORE&season_id={monthly_id}",
                headers=headers,
            )
            assert derived.status_code == 200
            assert derived.json()["data"]["period_type"] == "MONTHLY"
            assert derived.json()["data"]["season_id"] == monthly_id

            unknown = client.get(
                "/api/v1/leaderboard?board_type=EXPLORE&season_id=WEEKLY-19990104",
                headers=headers,
            )
            assert unknown.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_leaderboard_recompute_rebuilds_snapshot_without_touching_ledger(monkeypatch) -> None:
    """GDD 13.6: recompute from the ledger, never rewrite score_events."""
    from app.core.config import get_settings

    season_id = "WEEKLY-19990104"
    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    monkeypatch.setattr(get_settings(), "internal_api_key", "test-recompute-key")
    _db_exec([
        ("""
            INSERT INTO seasons
                (season_id, season_type, start_at_utc, end_at_utc,
                 status, settlement_status)
            VALUES
                (:season_id, 'WEEKLY', '1999-01-04T00:00:00Z',
                 '1999-01-11T00:00:00Z', 'ACTIVE', 'PENDING')
            ON CONFLICT (season_id) DO NOTHING
        """, {"season_id": season_id}),
    ])
    try:
        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"wx_code": str(uuid4()), "request_id": "recompute-login"},
            )
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
            player_id = client.get("/api/v1/player/me", headers=headers).json()["data"][
                "player_id"
            ]

            _db_exec([
                ("""
                    INSERT INTO score_events
                        (player_id, board_type, period_id, delta, reason,
                         source_event_id, idempotency_key, created_at_utc)
                    VALUES
                        (:player_id, 'EXPLORE', :season_id, 5, 'EXP_DISCOVER',
                         'recompute-a', 'recompute-a', now()),
                        (:player_id, 'EXPLORE', :season_id, 3, 'EXP_DISCOVER',
                         'recompute-b', 'recompute-b', now())
                    ON CONFLICT (board_type, period_id, idempotency_key) DO NOTHING
                """, {"player_id": player_id, "season_id": season_id}),
                ("""
                    INSERT INTO leaderboard_snapshots
                        (season_id, board_type, player_id, score, rank, snapshot_at_utc)
                    VALUES (:season_id, 'EXPLORE', :player_id, 99, 1, now())
                    ON CONFLICT (season_id, board_type, player_id)
                    DO UPDATE SET score = 99, rank = 1, snapshot_at_utc = now()
                """, {"season_id": season_id, "player_id": player_id}),
            ])

            dry_run = client.post(
                f"/api/v1/internal/leaderboard/{season_id}/recompute",
                headers={"X-Internal-API-Key": "test-recompute-key"},
                json={"board_type": "EXPLORE", "apply": False},
            )
            assert dry_run.status_code == 200
            dry = dry_run.json()["data"]
            assert dry["applied"] is False
            assert dry["difference_count"] == 1
            assert dry["differences"][0]["snapshot_score"] == 99
            assert dry["differences"][0]["recomputed_score"] == 8
            unchanged = _db_fetch(
                "SELECT score FROM leaderboard_snapshots WHERE season_id = :season_id"
                " AND board_type = 'EXPLORE' AND player_id = :player_id",
                {"season_id": season_id, "player_id": player_id},
            )
            assert unchanged[0]["score"] == 99

            applied = client.post(
                f"/api/v1/internal/leaderboard/{season_id}/recompute",
                headers={"X-Internal-API-Key": "test-recompute-key"},
                json={"board_type": "EXPLORE", "apply": True},
            )
            assert applied.status_code == 200
            assert applied.json()["data"]["applied"] is True
            rebuilt = _db_fetch(
                "SELECT score FROM leaderboard_snapshots WHERE season_id = :season_id"
                " AND board_type = 'EXPLORE' AND player_id = :player_id",
                {"season_id": season_id, "player_id": player_id},
            )
            assert rebuilt[0]["score"] == 8

            settled = client.post(
                f"/api/v1/internal/leaderboard/{season_id}/recompute",
                headers={"X-Internal-API-Key": "test-recompute-key"},
                json={"board_type": "EXPLORE", "apply": True},
            )
            assert settled.json()["data"]["difference_count"] == 0

            ledger = _db_fetch(
                "SELECT COUNT(*) AS total FROM score_events WHERE period_id = :season_id",
                {"season_id": season_id},
            )
            assert ledger[0]["total"] == 2
            audit = _db_fetch(
                "SELECT COUNT(*) AS total FROM actions_log"
                " WHERE action_type = 'LEADERBOARD_RECOMPUTE'"
                " AND payload->>'season_id' = :season_id",
                {"season_id": season_id},
            )
            assert audit[0]["total"] == 1

            denied = client.post(
                f"/api/v1/internal/leaderboard/{season_id}/recompute",
                headers={"X-Internal-API-Key": "wrong-key"},
                json={"board_type": "EXPLORE"},
            )
            assert denied.status_code == 401
    finally:
        _db_exec([
            ("DELETE FROM score_events WHERE period_id = :season_id", {"season_id": season_id}),
            (
                "DELETE FROM leaderboard_snapshots WHERE season_id = :season_id",
                {"season_id": season_id},
            ),
            (
                "DELETE FROM actions_log WHERE action_type = 'LEADERBOARD_RECOMPUTE'"
                " AND payload->>'season_id' = :season_id",
                {"season_id": season_id},
            ),
            ("DELETE FROM seasons WHERE season_id = :season_id", {"season_id": season_id}),
        ])
        app.dependency_overrides.clear()


def test_score_threshold_condition_grants_once_per_period() -> None:
    """GDD 11.7: SCORE conditions are evaluated against the running total."""
    import json
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.progress.repository import _write_score_event

    app.dependency_overrides[get_wechat_code_provider] = lambda: FakeWeChatProvider()
    player_id: UUID | None = None
    try:
        # Seeding lives inside the try block: an exception here must not leave the
        # shared catalogues READY and the mechanism positions zeroed for later tests.
        _set_test_content(True)
        _db_exec([
            ("""
                INSERT INTO rewards
                    (reward_id, reward_type, reward_name, condition_ref,
                     grant_mode, payload, is_paid, is_enabled)
                VALUES
                    ('TEST-SCORE-REWARD', 'RT_BADGE', '积分阈值徽章',
                     'TEST-SCORE-CONDITION', 'AUTO', '{}'::jsonb, false, true)
                ON CONFLICT (reward_id) DO NOTHING
            """, None),
            ("""
                INSERT INTO reward_conditions
                    (condition_id, trigger_type, condition_config,
                     reward_id, is_enabled, config_status)
                VALUES
                    ('TEST-SCORE-CONDITION', 'SCORE', CAST(:config AS jsonb),
                     'TEST-SCORE-REWARD', true, 'READY')
                ON CONFLICT (condition_id) DO UPDATE
                SET trigger_type = 'SCORE',
                    condition_config = CAST(:config AS jsonb),
                    is_enabled = true, config_status = 'READY'
            """, {"config": json.dumps({"board_type": "EXPLORE", "score_threshold": 8})}),
        ])

        with TestClient(app) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"wx_code": str(uuid4()), "request_id": "score-condition-login"},
            )
            assert login.status_code == 200
            headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
            player_id = UUID(
                client.get("/api/v1/player/me", headers=headers).json()["data"]["player_id"]
            )

        async def write_events() -> None:
            # A dedicated engine, not the application's: the app engine was created on
            # the TestClient event loop and reuse from asyncio.run raises "attached to
            # a different loop", which also poisons the pool for later tests.
            local_engine = create_async_engine(get_settings().database_url)
            try:
                async with AsyncSession(local_engine) as session:
                    for index in range(3):
                        await _write_score_event(
                            session,
                            player_id,
                            "EXP_DISCOVER",
                            f"score-condition-{index}",
                            None,
                            f"score-condition-{index}",
                        )
                    await session.commit()
            finally:
                await local_engine.dispose()

        asyncio.run(write_events())

        grants = _db_fetch(
            "SELECT COUNT(*) AS total FROM player_rewards"
            " WHERE player_id = :player_id AND reward_id = 'TEST-SCORE-REWARD'",
            {"player_id": player_id},
        )
        # 3 x 5 points crosses the threshold of 8 on the second event; the third must
        # not pay out again. One grant in total also proves the weekly and monthly
        # periods do not each pay for the same crossing.
        assert grants[0]["total"] == 1
        totals = _db_fetch(
            "SELECT COALESCE(SUM(delta), 0) AS total FROM score_events"
            " WHERE player_id = :player_id AND board_type = 'EXPLORE'",
            {"player_id": player_id},
        )
        assert totals[0]["total"] >= 8
    finally:
        _db_exec([
            ("DELETE FROM player_rewards WHERE reward_id = 'TEST-SCORE-REWARD'", None),
            (
                "DELETE FROM reward_conditions WHERE condition_id = 'TEST-SCORE-CONDITION'",
                None,
            ),
            ("DELETE FROM rewards WHERE reward_id = 'TEST-SCORE-REWARD'", None),
        ] + ([(
            "DELETE FROM score_events WHERE player_id = :player_id",
            {"player_id": player_id},
        )] if player_id else []))
        _set_test_content(False)
        app.dependency_overrides.clear()
