import asyncio
import json
import logging
from typing import Any

import aio_pika
from aio_pika.abc import AbstractIncomingMessage

from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
        queue = await channel.declare_queue(settings.rabbitmq_task_queue, durable=True)
        logger.info("Worker consuming queue=%s", settings.rabbitmq_task_queue)
        await queue.consume(handle_message)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
