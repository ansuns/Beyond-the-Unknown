# ruff: noqa: I001

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import aio_pika
from aio_pika import DeliveryMode, ExchangeType
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage, AbstractRobustChannel
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
OUTBOX_BATCH_SIZE = 25
OUTBOX_POLL_SECONDS = 1.0
SEASON_SCHEDULER_SECONDS = 5.0

TaskHandler = Callable[[dict[str, Any]], Awaitable[None]]


class PermanentTaskError(ValueError):
    """A malformed or unsupported task that must be dead-lettered."""


async def handle_ping(envelope: dict[str, Any]) -> None:
    logger.info("Accepted worker.ping task_id=%s", envelope["task_id"])


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
                raise PermanentTaskError(f"Unregistered task type: {task_type}")

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


async def handle_outbox_task(envelope: dict[str, Any]) -> None:
    try:
        await _process_outbox_task(envelope)
    except PermanentTaskError:
        raise
    except Exception as error:
        exhausted = await _schedule_retry(UUID(envelope["task_id"]), error)
        if exhausted:
            raise PermanentTaskError(
                f"Outbox task exhausted retries task_id={envelope['task_id']}"
            ) from error
        logger.exception(
            "Outbox task deferred task_id=%s task_type=%s",
            envelope["task_id"],
            envelope["task_type"],
        )


TASK_HANDLERS: dict[str, TaskHandler] = {
    "worker.ping": handle_ping,
    "season.finalize": handle_outbox_task,
    "season.auto_approve": handle_outbox_task,
}


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
    if not isinstance(envelope["task_id"], str) or not envelope["task_id"]:
        raise PermanentTaskError("Task task_id must be a non-empty string")
    if not isinstance(envelope["task_type"], str):
        raise PermanentTaskError("Task task_type must be a string")
    if not isinstance(envelope["idempotency_key"], str) or not envelope["idempotency_key"]:
        raise PermanentTaskError("Task idempotency_key must be a non-empty string")
    if not isinstance(envelope["payload"], dict):
        raise PermanentTaskError("Task payload must be an object")
    if envelope["task_type"] not in TASK_HANDLERS:
        raise PermanentTaskError(f"Unregistered task type: {envelope['task_type']}")
    if envelope["task_type"] in {"season.finalize", "season.auto_approve"}:
        try:
            UUID(envelope["task_id"])
        except ValueError as error:
            raise PermanentTaskError("Outbox task_id must be a UUID") from error
        if not isinstance(envelope["payload"].get("season_id"), str):
            raise PermanentTaskError("Season task payload requires season_id")
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
        delivery_mode=DeliveryMode.PERSISTENT,
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


async def _publish_outbox_batch(channel: AbstractRobustChannel) -> int:
    settings = get_settings()
    published = 0
    async with SessionFactory() as session:
        async with session.begin():
            rows = (
                await session.execute(
                    text("""
                        SELECT task_id, task_type, schema_version, payload,
                               idempotency_key, attempts, max_attempts
                        FROM task_outbox
                        WHERE status = 'PENDING' AND available_at_utc <= now()
                        ORDER BY created_at_utc
                        LIMIT :batch_size
                        FOR UPDATE SKIP LOCKED
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
                message = aio_pika.Message(
                    body=json.dumps(envelope, separators=(",", ":")).encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id=str(row["task_id"]),
                )
                try:
                    confirmation = await channel.default_exchange.publish(
                        message,
                        routing_key=settings.rabbitmq_task_queue,
                        mandatory=True,
                    )
                    if confirmation is False:
                        raise RuntimeError(
                            f"RabbitMQ did not confirm outbox task {row['task_id']}"
                        )
                except Exception as error:
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
                            "task_id": row["task_id"],
                            "attempts": attempts,
                            "status": "FAILED" if failed else "PENDING",
                            "available_at": datetime.now(UTC)
                            + timedelta(seconds=delay_seconds),
                            "last_error": str(error)[:2000],
                        },
                    )
                    logger.exception("Outbox publish failed task_id=%s", row["task_id"])
                    continue

                await session.execute(
                    text("""
                        UPDATE task_outbox
                        SET status = 'PUBLISHED',
                            published_at_utc = now(),
                            updated_at_utc = now(),
                            last_error = NULL
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
            "Worker consuming queue=%s retry_queue=%s dead_letter_queue=%s",
            settings.rabbitmq_task_queue,
            settings.rabbitmq_task_queue + RETRY_QUEUE_SUFFIX,
            DEAD_LETTER_QUEUE,
        )
        await queue.consume(consume)
        await asyncio.gather(
            outbox_relay_loop(channel),
            season_scheduler_loop(),
        )


if __name__ == "__main__":
    asyncio.run(main())
