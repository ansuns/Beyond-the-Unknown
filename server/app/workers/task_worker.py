import asyncio
import json
import logging
from typing import Any

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractIncomingMessage

from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEAD_LETTER_EXCHANGE = "game.tasks.dlx"
DEAD_LETTER_QUEUE = "game.tasks.dlq"


async def handle_message(message: AbstractIncomingMessage) -> None:
    async with message.process(requeue=False):
        envelope: dict[str, Any] = json.loads(message.body)
        required = {"schema_version", "task_id", "task_type", "idempotency_key", "payload"}
        missing = required.difference(envelope)
        if missing:
            raise ValueError(f"Task envelope missing fields: {sorted(missing)}")
        if envelope["task_type"] != "worker.ping":
            raise ValueError(f"Unregistered task type: {envelope['task_type']}")
        logger.info("Accepted worker.ping task_id=%s", envelope["task_id"])


async def main() -> None:
    settings = get_settings()
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
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
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
