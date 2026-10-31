"""Retry and dead-letter behaviour against a real RabbitMQ broker.

``tests/test_task_worker.py`` drives ``process_message`` with fake messages and
fake exchanges, which proves the branches but not the topology: whether the
retry queue really dead-letters back to the task queue after its TTL, whether
the headers survive both hops, and whether an exhausted message actually lands
in the DLQ. Those are properties of the broker, so this module runs the real
thing through the worker's own ``declare_topology`` and ``process_message``.

Set ``TEST_RABBITMQ_URL`` to enable it. The queues are declared under sandbox
names so a developer running the worker locally is not disturbed.
"""

import asyncio
import json
import os
import time
from typing import Any

import aio_pika
import pytest
from aio_pika import DeliveryMode

from app.workers import task_worker

pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_RABBITMQ_URL"),
    reason="Set TEST_RABBITMQ_URL to run RabbitMQ integration tests",
)

MAX_RETRIES = 2
SANDBOX = task_worker.topology_from_settings().sandbox("test")


class FailingHandler:
    """A task that always fails, recording how many times it was attempted."""

    def __init__(self) -> None:
        self.attempts = 0

    async def __call__(self, envelope: dict[str, Any]) -> None:
        self.attempts += 1
        raise RuntimeError("simulated downstream failure")


def _envelope(task_id: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": task_id,
        "task_type": "worker.ping",
        "idempotency_key": f"idem-{task_id}",
        "payload": {},
    }


async def _wait_for_message(
    queue: aio_pika.abc.AbstractQueue, timeout: float
) -> aio_pika.abc.AbstractIncomingMessage | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        message = await queue.get(no_ack=False, fail=False)
        if message is not None:
            return message
        await asyncio.sleep(0.1)
    return None


def test_failed_task_retries_then_lands_in_dead_letter_queue() -> None:
    async def scenario() -> None:
        connection = await aio_pika.connect_robust(os.environ["TEST_RABBITMQ_URL"])
        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            queue, retry_exchange, dead_letter_exchange = await task_worker.declare_topology(
                channel, SANDBOX
            )
            dead_letter_queue = await channel.get_queue(SANDBOX.dead_letter_queue)
            await queue.purge()
            await dead_letter_queue.purge()

            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=json.dumps(_envelope("retry-then-dlq-0001")).encode(),
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id="retry-then-dlq-0001",
                ),
                routing_key=SANDBOX.task_queue,
                mandatory=True,
            )

            handler = FailingHandler()
            seen_retry_counts: list[int] = []

            # Attempt 0 fails -> retry 1, attempt 1 fails -> retry 2,
            # attempt 2 hits max_retries -> DLQ. The retry queue's TTL has to
            # expire before the message is available again; that delay is the
            # part a fake exchange cannot verify.
            for _ in range(MAX_RETRIES + 1):
                message = await _wait_for_message(queue, timeout=5.0)
                assert message is not None, "retried message never returned to the task queue"
                seen_retry_counts.append(int((message.headers or {}).get("x-retry-count", 0)))
                await task_worker.process_message(
                    message,
                    retry_exchange,
                    dead_letter_exchange,
                    SANDBOX.task_queue,
                    max_retries=MAX_RETRIES,
                    handler=handler,
                )

            assert handler.attempts == MAX_RETRIES + 1
            assert seen_retry_counts == [0, 1, 2]

            dead = await _wait_for_message(dead_letter_queue, timeout=5.0)
            assert dead is not None, "exhausted task never reached the dead-letter queue"
            assert dead.message_id == "retry-then-dlq-0001"
            reason = (dead.headers or {}).get("x-failure-reason") or ""
            assert "simulated downstream failure" in reason
            await dead.ack()

            # Nothing may be left behind: an exhausted task that also stays in
            # the task queue would be retried forever.
            assert await queue.get(no_ack=False, fail=False) is None

    asyncio.run(scenario())


def test_malformed_task_goes_to_dead_letter_queue_without_retry() -> None:
    async def scenario() -> None:
        connection = await aio_pika.connect_robust(os.environ["TEST_RABBITMQ_URL"])
        async with connection:
            channel = await connection.channel(publisher_confirms=True)
            queue, retry_exchange, dead_letter_exchange = await task_worker.declare_topology(
                channel, SANDBOX
            )
            dead_letter_queue = await channel.get_queue(SANDBOX.dead_letter_queue)
            retry_queue = await channel.get_queue(SANDBOX.retry_queue)
            await queue.purge()
            await dead_letter_queue.purge()

            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=b"{not json",
                    content_type="application/json",
                    delivery_mode=DeliveryMode.PERSISTENT,
                    message_id="malformed-0001",
                ),
                routing_key=SANDBOX.task_queue,
                mandatory=True,
            )

            handler = FailingHandler()
            message = await _wait_for_message(queue, timeout=5.0)
            assert message is not None
            await task_worker.process_message(
                message,
                retry_exchange,
                dead_letter_exchange,
                SANDBOX.task_queue,
                max_retries=MAX_RETRIES,
                handler=handler,
            )

            assert handler.attempts == 0, "a malformed envelope must never reach a handler"
            assert await retry_queue.get(no_ack=False, fail=False) is None

            dead = await _wait_for_message(dead_letter_queue, timeout=5.0)
            assert dead is not None
            reason = (dead.headers or {}).get("x-failure-reason") or ""
            assert "UTF-8 JSON" in reason
            await dead.ack()

    asyncio.run(scenario())
