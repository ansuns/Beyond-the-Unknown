import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractExchange
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.workers.task_worker import DEAD_LETTER_EXCHANGE, DEAD_LETTER_QUEUE

logger = logging.getLogger(__name__)

BATCH_SIZE = 25


async def dispatch_pending_once(
    session_factory: async_sessionmaker[AsyncSession],
    exchange: AbstractExchange,
    task_queue: str,
    batch_size: int = BATCH_SIZE,
) -> int:
    published_count = 0
    async with session_factory() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    text("""
                        SELECT event_id, event_type, payload, idempotency_key, attempts
                        FROM outbox_events
                        WHERE published_at IS NULL AND next_attempt_at <= now()
                        ORDER BY created_at, event_id
                        FOR UPDATE SKIP LOCKED
                        LIMIT :batch_size
                    """),
                    {"batch_size": batch_size},
                )
            ).mappings().all()

            for row in rows:
                task_id = str(row["event_id"])
                envelope: dict[str, Any] = {
                    "schema_version": 1,
                    "task_id": task_id,
                    "task_type": row["event_type"],
                    "idempotency_key": row["idempotency_key"],
                    "payload": row["payload"],
                }
                message = aio_pika.Message(
                    body=json.dumps(envelope, separators=(",", ":"), default=str).encode(),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=task_id,
                    type=row["event_type"],
                    headers={"x-outbox-event-id": task_id},
                )
                attempts = row["attempts"] + 1
                try:
                    confirmation = await exchange.publish(
                        message, routing_key=task_queue, mandatory=True
                    )
                    if confirmation is False:
                        raise RuntimeError("RabbitMQ did not confirm outbox publication")
                except Exception as error:
                    retry_delay = min(300, 2 ** min(attempts, 8))
                    await session.execute(
                        text("""
                            UPDATE outbox_events
                            SET attempts = :attempts,
                                next_attempt_at = :next_attempt_at,
                                last_error = :last_error
                            WHERE event_id = :event_id
                        """),
                        {
                            "attempts": attempts,
                            "next_attempt_at": datetime.now(UTC)
                            + timedelta(seconds=retry_delay),
                            "last_error": str(error)[:500],
                            "event_id": row["event_id"],
                        },
                    )
                    logger.exception("Outbox publish failed event_id=%s", task_id)
                    continue

                await session.execute(
                    text("""
                        UPDATE outbox_events
                        SET attempts = :attempts,
                            published_at = now(),
                            last_error = NULL
                        WHERE event_id = :event_id
                    """),
                    {"attempts": attempts, "event_id": row["event_id"]},
                )
                published_count += 1
    return published_count


async def main() -> None:
    settings = get_settings()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        dead_letter_exchange = await channel.declare_exchange(
            DEAD_LETTER_EXCHANGE, ExchangeType.DIRECT, durable=True
        )
        dead_letter_queue = await channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
        await dead_letter_queue.bind(dead_letter_exchange, routing_key="failed")
        await channel.declare_queue(
            settings.rabbitmq_task_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": "failed",
            },
        )
        logger.info("Outbox dispatcher started queue=%s", settings.rabbitmq_task_queue)
        while True:
            try:
                published = await dispatch_pending_once(
                    SessionFactory,
                    channel.default_exchange,
                    settings.rabbitmq_task_queue,
                )
            except Exception:
                logger.exception("Outbox dispatch cycle failed")
                published = 0
            await asyncio.sleep(0.1 if published else 1.0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
