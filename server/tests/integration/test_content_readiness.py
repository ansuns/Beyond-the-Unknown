import asyncio
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.tools.content_readiness import build_content_readiness_report

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("TEST_DATABASE_URL"),
        reason=(
            "Set TEST_DATABASE_URL and apply Alembic migrations "
            "for PostgreSQL integration tests"
        ),
    ),
]


def test_seeded_game_content_is_reported_as_blocked_until_tuned() -> None:
    async def run() -> dict:
        engine = create_async_engine(get_settings().database_url)
        try:
            async with engine.connect() as connection:
                return await build_content_readiness_report(connection)
        finally:
            await engine.dispose()

    report = asyncio.run(run())

    assert report["status"] == "BLOCKED"
    assert report["blocker_count"] > 0
    assert "rule_tuning" in report["categories"]
    assert "mechanism_content" in report["categories"]
