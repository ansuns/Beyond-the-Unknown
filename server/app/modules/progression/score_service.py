from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _ensure_periods(session: AsyncSession, now: datetime) -> list[str]:
    day_start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    week_start = day_start - timedelta(days=day_start.weekday())
    week_end = week_start + timedelta(days=7)
    month_start = day_start.replace(day=1)
    if month_start.month == 12:
        month_end = month_start.replace(year=month_start.year + 1, month=1)
    else:
        month_end = month_start.replace(month=month_start.month + 1)
    periods = [
        (f"WEEKLY-{week_start:%Y%m%d}", "WEEKLY", week_start, week_end),
        (f"MONTHLY-{month_start:%Y%m}", "MONTHLY", month_start, month_end),
    ]
    await session.execute(
        text("""
            UPDATE seasons SET status = 'CLOSED'
            WHERE status = 'ACTIVE' AND end_at_utc <= :now
        """),
        {"now": now},
    )
    for season_id, season_type, start_at, end_at in periods:
        await session.execute(
            text("""
                INSERT INTO seasons
                    (season_id, season_type, start_at_utc, end_at_utc, status)
                VALUES (:season_id, :season_type, :start_at, :end_at, 'ACTIVE')
                ON CONFLICT (season_id) DO UPDATE
                SET status = CASE
                    WHEN seasons.status = 'SCHEDULED' THEN 'ACTIVE'::season_status
                    ELSE seasons.status
                END
            """),
            {
                "season_id": season_id,
                "season_type": season_type,
                "start_at": start_at,
                "end_at": end_at,
            },
        )
    rows = (
        await session.execute(
            text("""
                SELECT season_id FROM seasons
                WHERE status = 'ACTIVE'
                  AND start_at_utc <= :now AND end_at_utc > :now
            """),
            {"now": now},
        )
    ).scalars().all()
    return list(rows)


async def award_score_if_configured(
    session: AsyncSession,
    player_id: UUID,
    reason: str,
    source_event_id: str,
    run_id: UUID | None,
) -> list[dict[str, Any]]:
    config = (
        await session.execute(
            text("""
                SELECT board_type::text AS board_type, delta, config_status
                FROM score_award_config WHERE reason = :reason
            """),
            {"reason": reason},
        )
    ).mappings().one_or_none()
    if config is None or config["config_status"] != "READY" or config["delta"] is None:
        return []
    now = datetime.now(UTC)
    periods = await _ensure_periods(session, now)
    awards = []
    for period_id in periods:
        key = f"{reason}:{player_id}:{source_event_id}:{period_id}"
        event_id = (
            await session.execute(
                text("""
                    INSERT INTO score_events
                        (player_id, board_type, period_id, delta, reason,
                         source_event_id, run_id, idempotency_key)
                    VALUES
                        (:player_id, :board_type, :period_id, :delta, :reason,
                         :source_event_id, :run_id, :idempotency_key)
                    ON CONFLICT (board_type, period_id, idempotency_key) DO NOTHING
                    RETURNING event_id
                """),
                {
                    "player_id": player_id,
                    "board_type": config["board_type"],
                    "period_id": period_id,
                    "delta": config["delta"],
                    "reason": reason,
                    "source_event_id": source_event_id,
                    "run_id": run_id,
                    "idempotency_key": key,
                },
            )
        ).scalar_one_or_none()
        if event_id is not None:
            awards.append(
                {
                    "event_id": str(event_id),
                    "board_type": config["board_type"],
                    "period_id": period_id,
                    "delta": int(config["delta"]),
                }
            )
    return awards
