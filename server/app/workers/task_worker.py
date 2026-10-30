import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage

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
RETRY_EXCHANGE = "game.tasks.retry.x"
RETRY_QUEUE_SUFFIX = ".retry"
RETRY_ROUTING_KEY = "retry"

TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]


class PermanentTaskError(ValueError):
    """A task envelope or task type that must not be retried."""


async def handle_ping(envelope: dict[str, Any]) -> None:
    logger.info("Accepted worker.ping task_id=%s", envelope["task_id"])


TASK_HANDLERS: dict[str, TaskHandler] = {"worker.ping": handle_ping}


def decode_envelope(body: bytes) -> dict[str, Any]:
    try:
        envelope = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PermanentTaskError("Task body is not valid UTF-8 JSON") from error
    if not isinstance(envelope, dict):
        raise PermanentTaskError("Task envelope must be a JSON object")
    required = {"schema_version", "task_id", "task_type", "idempotency_key", "payload"}
    missing = required.difference(envelope)
    if missing:
        raise PermanentTaskError(f"Task envelope missing fields: {sorted(missing)}")
    if envelope["schema_version"] != 1:
        raise PermanentTaskError("Unsupported task schema_version")
    if not isinstance(envelope["task_type"], str):
        raise PermanentTaskError("Task task_type must be a string")
    if not isinstance(envelope["idempotency_key"], str) or not envelope["idempotency_key"]:
        raise PermanentTaskError("Task idempotency_key must be a non-empty string")
    if not isinstance(envelope["payload"], dict):
        raise PermanentTaskError("Task payload must be an object")
    if envelope["task_type"] not in TASK_HANDLERS:
        raise PermanentTaskError(f"Unregistered task type: {envelope['task_type']}")
    return envelope


async def _publish_confirmed(
    exchange: AbstractExchange,
    routing_key: str,
    message: AbstractIncomingMessage,
    headers: dict[str, Any],
) -> None:
    outgoing = aio_pika.Message(
        body=message.body,
        content_type=message.content_type or "application/json",
        content_encoding=message.content_encoding,
        headers=headers,
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        correlation_id=message.correlation_id,
        message_id=message.message_id,
        type=message.type,
    )
    confirmation = await exchange.publish(outgoing, routing_key=routing_key, mandatory=True)
    if confirmation is False:
        raise RuntimeError("RabbitMQ publisher did not confirm task publication")


async def process_message(
    message: AbstractIncomingMessage,
    retry_exchange: AbstractExchange,
    dead_letter_exchange: AbstractExchange,
    task_queue: str,
    max_retries: int = 3,
    handler: TaskHandler | None = None,
) -> None:
    try:
        envelope = decode_envelope(message.body)
        task_handler = handler or TASK_HANDLERS[envelope["task_type"]]
        await task_handler(envelope)
    except PermanentTaskError as error:
        headers = dict(message.headers or {})
        headers["x-failure-reason"] = str(error)[:200]
        try:
            await _publish_confirmed(dead_letter_exchange, "failed", message, headers)
        except Exception:
            logger.exception("Failed to publish permanent task failure to DLQ")
            await message.nack(requeue=True)
            return
        await message.ack()
        return
    except Exception as error:
        headers = dict(message.headers or {})
        try:
            retry_count = max(0, int(headers.get("x-retry-count", 0)))
        except (TypeError, ValueError):
            retry_count = 0
        headers["x-failure-reason"] = str(error)[:200]
        if retry_count >= max_retries:
            try:
                await _publish_confirmed(dead_letter_exchange, "failed", message, headers)
            except Exception:
                logger.exception("Failed to publish exhausted task to DLQ")
                await message.nack(requeue=True)
                return
            await message.ack()
            logger.error("Task exhausted retries task_id=%s", message.message_id)
            return

        headers["x-retry-count"] = retry_count + 1
        try:
            await _publish_confirmed(retry_exchange, RETRY_ROUTING_KEY, message, headers)
        except Exception:
            logger.exception("Failed to publish task retry")
            await message.nack(requeue=True)
            return
        await message.ack()
        logger.warning(
            "Task scheduled for retry task_id=%s retry=%s/%s",
            message.message_id,
            retry_count + 1,
            max_retries,
        )
        return

    await message.ack()



async def _process_outbox_task(envelope: dict[str, Any]) -> None:
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
                raise PermanentTaskError(f"Unregistered outbox task: {task_type}")
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


async def _record_outbox_failure(task_id: UUID, error: Exception) -> None:
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
                return
            attempts = row["attempts"] + 1
            status = "FAILED" if attempts >= row["max_attempts"] else "PUBLISHED"
            await session.execute(
                text("""
                    UPDATE task_outbox
                    SET attempts = :attempts, status = :status,
                        last_error = :last_error, updated_at_utc = now()
                    WHERE task_id = :task_id
                """),
                {
                    "task_id": task_id,
                    "attempts": attempts,
                    "status": status,
                    "last_error": str(error)[:2000],
                },
            )


async def handle_season_task(envelope: dict[str, Any]) -> None:
    task_id = UUID(envelope["task_id"])
    try:
        await _process_outbox_task(envelope)
    except Exception as error:
        await _record_outbox_failure(task_id, error)
        raise


TASK_HANDLERS["season.finalize"] = handle_season_task
TASK_HANDLERS["season.auto_approve"] = handle_season_task


async def _publish_outbox_batch(exchange: AbstractExchange) -> int:
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
                        LIMIT 25
                        FOR UPDATE SKIP LOCKED
                    """)
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
                confirmation = await exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(envelope, separators=(",", ":")).encode("utf-8"),
                        content_type="application/json",
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        message_id=str(row["task_id"]),
                        type=row["task_type"],
                    ),
                    routing_key=settings.rabbitmq_task_queue,
                    mandatory=True,
                )
                if confirmation is False:
                    raise RuntimeError("RabbitMQ did not confirm outbox publication")
                await session.execute(
                    text("""
                        UPDATE task_outbox
                        SET status = 'PUBLISHED', published_at_utc = now(),
                            updated_at_utc = now()
                        WHERE task_id = :task_id
                    """),
                    {"task_id": row["task_id"]},
                )
                published += 1
    return published


async def outbox_relay_loop(exchange: AbstractExchange) -> None:
    while True:
        try:
            count = await _publish_outbox_batch(exchange)
            if count:
                logger.info("Published %s transactional outbox tasks", count)
        except Exception:
            logger.exception("Transactional outbox relay failed")
        await asyncio.sleep(1.0)


async def season_scheduler_loop() -> None:
    while True:
        try:
            async with SessionFactory() as session:
                async with session.begin():
                    count = await enqueue_due_seasons(session)
                    if count:
                        logger.info("Enqueued %s due season finalizations", count)
        except Exception:
            logger.exception("Season scheduler failed")
        await asyncio.sleep(5.0)


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

        retry_exchange = await channel.declare_exchange(
            RETRY_EXCHANGE, ExchangeType.DIRECT, durable=True
        )
        retry_queue = await channel.declare_queue(
            settings.rabbitmq_task_queue + RETRY_QUEUE_SUFFIX,
            durable=True,
            arguments={
                "x-message-ttl": settings.rabbitmq_retry_delay_ms,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": settings.rabbitmq_task_queue,
            },
        )
        await retry_queue.bind(retry_exchange, routing_key=RETRY_ROUTING_KEY)

        queue = await channel.declare_queue(
            settings.rabbitmq_task_queue,
            durable=True,
            arguments={
                "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
                "x-dead-letter-routing-key": "failed",
            },
        )

        async def consume(message: AbstractIncomingMessage) -> None:
            await process_message(
                message,
                retry_exchange,
                dead_letter_exchange,
                settings.rabbitmq_task_queue,
                max_retries=settings.rabbitmq_max_retries,
            )

        logger.info(
            "Worker consuming queue=%s retry_queue=%s dead_letter_queue=%s max_retries=%s",
            settings.rabbitmq_task_queue,
            settings.rabbitmq_task_queue + RETRY_QUEUE_SUFFIX,
            DEAD_LETTER_QUEUE,
            settings.rabbitmq_max_retries,
        )
        await queue.consume(consume)
        await asyncio.gather(
            outbox_relay_loop(channel.default_exchange),
            season_scheduler_loop(),
        )


if __name__ == "__main__":
    asyncio.run(main())
