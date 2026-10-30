import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustChannel
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.modules.progress.season_service import (
    auto_approve_season,
    enqueue_due_seasons,
    finalize_season,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEAD_LETTER_EXCHANGE = "game.tasks.dlx"
DEAD_LETTER_QUEUE = "game.tasks.dlq"
OUTBOX_BATCH_SIZE = 25
OUTBOX_POLL_SECONDS = 1.0
SEASON_SCHEDULER_SECONDS = 5.0


async def _process_outbox_task(envelope: dict[str, Any]) -> None:
    if envelope.get("schema_version") != 1:
        raise ValueError("Unsupported task schema_version")
    task_id = UUID(envelope["task_id"])
    task_type = envelope["task_type"]
    idempotency_key = envelope["idempotency_key"]
    payload = envelope["payload"]

    async with SessionFactory() as session:
        async with session.begin():
            receipt = (
                await session.execute(
                    text("""
                        INSERT INTO worker_task_receipts
                            (task_id, task_type, idempotency_key)
                        VALUES (:task_id, :task_type, :idempotency_key)
                        ON CONFLICT DO NOTHING
                        RETURNING task_id
                    """),
                    {
                        "task_id": task_id,
                        "task_type": task_type,
                        "idempotency_key": idempotency_key,
                    },
                )
            ).scalar_one_or_none()
            if receipt is None:
                return

            if task_type == "season.finalize":
                await finalize_season(session, payload["season_id"])
            elif task_type == "season.auto_approve":
                await auto_approve_season(session, payload["season_id"])
            else:
                raise ValueError(f"Unregistered task type: {task_type}")

            await session.execute(
                text("""
                    UPDATE task_outbox
                    SET status = 'COMPLETED',
                        processed_at_utc = now(),
                        updated_at_utc = now(),
                        last_error = NULL
                    WHERE task_id = :task_id
                """),
                {"task_id": task_id},
            )


async def _schedule_retry(task_id: UUID, error: Exception) -> bool:
    async with SessionFactory() as session:
        async with session.begin():
            row = (
                await session.execute(
                    text("""
                        SELECT attempts, max_attempts
                        FROM task_outbox
                        WHERE task_id = :task_id
                        FOR UPDATE
                    """),
                    {"task_id": task_id},
                )
            ).mappings().one_or_none()
            if row is None:
                return True
            attempts = row["attempts"] + 1
            failed = attempts >= row["max_attempts"]
            delay_seconds = min(5 * (2 ** min(attempts - 1, 6)), 300)
            await session.execute(
                text("""
                    UPDATE task_outbox
                    SET attempts = :attempts,
                        status = :status,
                        available_at_utc = :available_at,
                        last_error = :last_error,
                        updated_at_utc = now()
                    WHERE task_id = :task_id
                """),
                {
                    "task_id": task_id,
                    "attempts": attempts,
                    "status": "FAILED" if failed else "PENDING",
                    "available_at": datetime.now(UTC) + timedelta(seconds=delay_seconds),
                    "last_error": str(error)[:2000],
                },
            )
            return failed


async def handle_message(message: AbstractIncomingMessage) -> None:
    async with message.process(requeue=False):
        envelope: dict[str, Any] = json.loads(message.body)
        required = {
            "schema_version",
            "task_id",
            "task_type",
            "idempotency_key",
            "payload",
        }
        missing = required.difference(envelope)
        if missing:
            raise ValueError(f"Task envelope missing fields: {sorted(missing)}")
        if envelope["task_type"] == "worker.ping":
            logger.info("Accepted worker.ping task_id=%s", envelope["task_id"])
            return
        task_id = UUID(envelope["task_id"])
        try:
            await _process_outbox_task(envelope)
        except Exception as exc:
            logger.exception(
                "Outbox task failed task_id=%s task_type=%s",
                task_id,
                envelope["task_type"],
            )
            exhausted = await _schedule_retry(task_id, exc)
            if exhausted:
                raise RuntimeError(
                    f"Outbox task exhausted retries task_id={task_id}"
                ) from exc


async def _publish_outbox_batch(channel: AbstractRobustChannel) -> int:
    settings = get_settings()
    published = 0
    async with SessionFactory() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    text("""
                        SELECT task_id, task_type, schema_version, payload,
                               idempotency_key
                        FROM task_outbox
                        WHERE status = 'PENDING' AND available_at_utc <= now()
                        ORDER BY created_at_utc
                        FOR UPDATE SKIP LOCKED
                        LIMIT :batch_size
                    """),
                    {"batch_size": OUTBOX_BATCH_SIZE},
                )
            ).mappings().all()
            for row in rows:
                envelope = {
                    "schema_version": row["schema_version"],
                    "task_id": str(row["task_id"]),
                    "task_type": row["task_type"],
                    "idempotency_key": row["idempotency_key"],
                    "payload": row["payload"],
                }
                confirmation = await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(envelope, separators=(",", ":")).encode("utf-8"),
                        content_type="application/json",
                        delivery_mode=DeliveryMode.PERSISTENT,
                        message_id=str(row["task_id"]),
                    ),
                    routing_key=settings.rabbitmq_task_queue,
                    mandatory=True,
                )
                if confirmation is False:
                    raise RuntimeError(
                        f"RabbitMQ did not confirm outbox task {row['task_id']}"
                    )
                await session.execute(
                    text("""
                        UPDATE task_outbox
                        SET status = 'PUBLISHED',
                            published_at_utc = now(),
                            updated_at_utc = now()
                        WHERE task_id = :task_id
                    """),
                    {"task_id": row["task_id"]},
                )
                published += 1
    return published


async def outbox_relay_loop(channel: AbstractRobustChannel) -> None:
    while True:
        try:
            count = await _publish_outbox_batch(channel)
            if count:
                logger.info("Published %s outbox tasks", count)
        except Exception:
            logger.exception("Outbox relay iteration failed")
        await asyncio.sleep(OUTBOX_POLL_SECONDS)


async def season_scheduler_loop() -> None:
    while True:
        try:
            async with SessionFactory() as session:
                async with session.begin():
                    count = await enqueue_due_seasons(session)
                    if count:
                        logger.info("Enqueued %s due season finalizations", count)
        except Exception:
            logger.exception("Season scheduler iteration failed")
        await asyncio.sleep(SEASON_SCHEDULER_SECONDS)


async def main() -> None:
    settings = get_settings()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel(publisher_confirms=True)
        await channel.set_qos(prefetch_count=10)
        dead_letter_exchange = await channel.declare_exchange(
            DEAD_LETTER_EXCHANGE, ExchangeType.DIRECT, durable=True
        )
        dead_letter_queue = await channel.declare_queue(DEAD_LETTER_QUEUE, durable=True)
        await dead_letter_queue.bind(dead_letter_exchange, routing_key="failed")
        queue = await channel.declare_queue(
            settings.rabbitmq_task_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": "failed",
            },
        )
        logger.info(
            "Worker consuming queue=%s dead_letter_queue=%s",
            settings.rabbitmq_task_queue,
            DEAD_LETTER_QUEUE,
        )
        await queue.consume(handle_message)
        await asyncio.gather(
            outbox_relay_loop(channel),
            season_scheduler_loop(),
        )


if __name__ == "__main__":
    asyncio.run(main())
