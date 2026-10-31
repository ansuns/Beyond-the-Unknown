"""Shared helpers for PostgreSQL integration tests.

Rule tuning lives in ``rule_catalog`` with ``config_status = 'TUNING_REQUIRED'``
until the designers sign off GDD 13.2, and the server refuses to cast with
unset numbers (503) rather than invent them. Tests that exercise real casting
therefore have to supply a temporary value and put the catalogue back
afterwards; that is what ``apply_rule_tuning`` does. The values below are
explicitly test values, not design values, and never reach a migration.
"""

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

TEST_COOLDOWN_MS = 5000
TEST_RADIUS = 2.0
TEST_DURATION_MS = 1000
TEST_LEASE_TIMEOUT_MS = 5000
TEST_COMBO_WINDOW_MS = 10000


def database_url() -> str:
    """Prefer the dedicated test database so a stray run cannot touch dev data."""
    return os.getenv("TEST_DATABASE_URL") or get_settings().database_url


def execute(statement: str, parameters: dict | None = None) -> None:
    async def run() -> None:
        engine = create_async_engine(database_url())
        try:
            async with engine.begin() as connection:
                await connection.execute(text(statement), parameters or {})
        finally:
            await engine.dispose()

    asyncio.run(run())


def apply_rule_tuning(ready: bool) -> None:
    """Switch the whole rule catalogue between test tuning and TUNING_REQUIRED."""
    if ready:
        execute(
            """
            UPDATE rule_catalog
            SET cooldown_ms = :cooldown, radius = :radius, duration_ms = :duration,
                lease_timeout_ms = :lease, config_status = 'READY'
            """,
            {
                "cooldown": TEST_COOLDOWN_MS,
                "radius": TEST_RADIUS,
                "duration": TEST_DURATION_MS,
                "lease": TEST_LEASE_TIMEOUT_MS,
            },
        )
        execute(
            """
            UPDATE combo_catalog
            SET time_window_ms = :window, config_status = 'READY'
            """,
            {"window": TEST_COMBO_WINDOW_MS},
        )
    else:
        execute(
            """
            UPDATE rule_catalog
            SET cooldown_ms = NULL, radius = NULL, duration_ms = NULL,
                lease_timeout_ms = NULL, config_status = 'TUNING_REQUIRED'
            """
        )
        execute(
            """
            UPDATE combo_catalog
            SET time_window_ms = NULL, config_status = 'TUNING_REQUIRED'
            """
        )
