import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class OutboxIdempotencyConflict(Exception):
    pass


async def enqueue_outbox_event(
    session: AsyncSession,
    event_type: str,
    payload: dict[str, Any],
    idempotency_key: str,
) -> UUID:
    if not event_type or len(event_type) > 100:
        raise ValueError("event_type must contain 1–100 characters")
    if not idempotency_key or len(idempotency_key) > 200:
        raise ValueError("idempotency_key must contain 1–200 characters")

    serialized_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    inserted = (
        await session.execute(
            text("""
                INSERT INTO outbox_events
                    (event_type, payload, idempotency_key)
                VALUES
                    (:event_type, CAST(:payload AS jsonb), :idempotency_key)
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING event_id
            """),
            {
                "event_type": event_type,
                "payload": serialized_payload,
                "idempotency_key": idempotency_key,
            },
        )
    ).scalar_one_or_none()
    if inserted is not None:
        return inserted

    existing = (
        await session.execute(
            text("""
                SELECT event_id, event_type, payload
                FROM outbox_events
                WHERE idempotency_key = :idempotency_key
                FOR UPDATE
            """),
            {"idempotency_key": idempotency_key},
        )
    ).mappings().one()
    if (
        existing["event_type"] != event_type
        or existing["payload"] != json.loads(serialized_payload)
    ):
        raise OutboxIdempotencyConflict
    return existing["event_id"]
