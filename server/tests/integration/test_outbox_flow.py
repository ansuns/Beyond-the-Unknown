import asyncio
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.modules.outbox.repository import (
    OutboxIdempotencyConflict,
    enqueue_outbox_event,
)
from app.workers.outbox_dispatcher import dispatch_pending_once

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


class FakeExchange:
    def __init__(self) -> None:
        self.published = []

    async def publish(self, message, routing_key: str, mandatory: bool = False) -> bool:
        self.published.append((message, routing_key, mandatory))
        return True


def test_outbox_event_is_transactional_idempotent_and_published() -> None:
    async def run() -> None:
        engine = create_async_engine(get_settings().database_url)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        key = f"outbox-test-{uuid4()}"
        event_id = None
        try:
            async with session_factory() as session:
                async with session.begin():
                    event_id = await enqueue_outbox_event(
                        session,
                        "game.level.settled",
                        {"result_id": "result-1", "level_id": "LV-ROOM-01"},
                        key,
                    )
                    duplicate = await enqueue_outbox_event(
                        session,
                        "game.level.settled",
                        {"result_id": "result-1", "level_id": "LV-ROOM-01"},
                        key,
                    )
                    assert duplicate == event_id
                    with pytest.raises(OutboxIdempotencyConflict):
                        await enqueue_outbox_event(
                            session,
                            "game.level.settled",
                            {"result_id": "different-result"},
                            key,
                        )

            exchange = FakeExchange()
            published_count = await dispatch_pending_once(
                session_factory, exchange, "game.tasks.v1", batch_size=100
            )
            assert published_count >= 1
            envelopes = [
                json.loads(message.body)
                for message, routing_key, mandatory in exchange.published
                if routing_key == "game.tasks.v1" and mandatory
            ]
            envelope = next(item for item in envelopes if item["idempotency_key"] == key)
            assert envelope["task_type"] == "game.level.settled"
            assert envelope["payload"]["result_id"] == "result-1"

            async with session_factory() as session:
                row = (
                    await session.execute(
                        text("""
                            SELECT published_at, attempts
                            FROM outbox_events
                            WHERE event_id = :event_id
                        """),
                        {"event_id": event_id},
                    )
                ).mappings().one()
                assert row["published_at"] is not None
                assert row["attempts"] == 1
        finally:
            if event_id is not None:
                async with engine.begin() as connection:
                    await connection.execute(
                        text("DELETE FROM outbox_events WHERE event_id = :event_id"),
                        {"event_id": event_id},
                    )
            await engine.dispose()

    asyncio.run(run())
