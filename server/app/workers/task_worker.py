import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractExchange, AbstractIncomingMessage

from app.core.config import get_settings

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
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
