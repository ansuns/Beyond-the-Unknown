import json
from typing import Any

import pytest

from app.workers.task_worker import process_message


class FakeIncomingMessage:
    def __init__(self, envelope: dict[str, Any], headers: dict[str, Any] | None = None):
        self.body = json.dumps(envelope).encode()
        self.headers = headers or {}
        self.content_type = "application/json"
        self.content_encoding = "utf-8"
        self.correlation_id = "correlation-1"
        self.message_id = envelope.get("task_id", "message-1")
        self.type = envelope.get("task_type", "worker.ping")
        self.acked = False
        self.nacked = False
        self.requeue: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool = False) -> None:
        self.nacked = True
        self.requeue = requeue


class FakeExchange:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.published: list[tuple[Any, str]] = []

    async def publish(self, message: Any, routing_key: str, mandatory: bool = False) -> bool:
        if self.fail:
            raise RuntimeError("broker publish unavailable")
        self.published.append((message, routing_key))
        return True


def valid_envelope() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": "task-1",
        "task_type": "worker.ping",
        "idempotency_key": "ping-1",
        "payload": {},
    }


@pytest.mark.asyncio
async def test_successful_task_is_acked_without_republish() -> None:
    message = FakeIncomingMessage(valid_envelope())
    retry = FakeExchange()
    dead = FakeExchange()

    await process_message(message, retry, dead, "game.tasks.v1")

    assert message.acked is True
    assert message.nacked is False
    assert retry.published == []
    assert dead.published == []


@pytest.mark.asyncio
async def test_transient_failure_is_published_to_retry_before_ack() -> None:
    message = FakeIncomingMessage(valid_envelope(), {"x-retry-count": 1})
    retry = FakeExchange()
    dead = FakeExchange()

    async def transient_failure(_: dict[str, Any]) -> None:
        raise RuntimeError("temporary dependency outage")

    await process_message(message, retry, dead, "game.tasks.v1", handler=transient_failure)

    assert message.acked is True
    assert message.nacked is False
    assert len(retry.published) == 1
    outgoing, routing_key = retry.published[0]
    assert routing_key == "retry"
    assert outgoing.headers["x-retry-count"] == 2
    assert outgoing.delivery_mode.value == 2
    assert dead.published == []


@pytest.mark.asyncio
async def test_exhausted_task_is_sent_to_dlq_before_ack() -> None:
    message = FakeIncomingMessage(valid_envelope(), {"x-retry-count": 3})
    retry = FakeExchange()
    dead = FakeExchange()

    async def transient_failure(_: dict[str, Any]) -> None:
        raise RuntimeError("still unavailable")

    await process_message(
        message,
        retry,
        dead,
        "game.tasks.v1",
        max_retries=3,
        handler=transient_failure,
    )

    assert message.acked is True
    assert retry.published == []
    assert len(dead.published) == 1
    outgoing, routing_key = dead.published[0]
    assert routing_key == "failed"
    assert outgoing.headers["x-retry-count"] == 3
    assert "still unavailable" in outgoing.headers["x-failure-reason"]


@pytest.mark.asyncio
async def test_malformed_envelope_goes_directly_to_dlq() -> None:
    message = FakeIncomingMessage({"task_id": "bad"})
    message.body = b"{not-json"
    retry = FakeExchange()
    dead = FakeExchange()

    await process_message(message, retry, dead, "game.tasks.v1")

    assert message.acked is True
    assert retry.published == []
    assert len(dead.published) == 1
    assert dead.published[0][1] == "failed"


@pytest.mark.asyncio
async def test_publish_failure_nacks_original_for_broker_redelivery() -> None:
    message = FakeIncomingMessage(valid_envelope())
    retry = FakeExchange(fail=True)
    dead = FakeExchange()

    async def transient_failure(_: dict[str, Any]) -> None:
        raise RuntimeError("temporary failure")

    await process_message(message, retry, dead, "game.tasks.v1", handler=transient_failure)

    assert message.acked is False
    assert message.nacked is True
    assert message.requeue is True
