"""Unified definitions for the three room gameplay event sources (GDD 11.1).

LOGIN, MOVE and RULE_CAST are the tutorial task's first three objectives and
they were the gap: the objectives existed in ``task_catalog.json`` but nothing
ever advanced them, so a new player could finish every room and still see
"初次踏入无界之地" stuck at 1/4.

Keep this module free of I/O: the rules for what counts as a valid event are
cheap to test and easy to read when they are plain functions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

MAX_SOURCE_ID_LENGTH = 128
MAX_PAYLOAD_BYTES = 2048


class LevelEventType(StrEnum):
    """Objective types this pipeline owns.

    The values are exactly the ``objective_type`` strings in the task
    catalogue; renaming one here silently stops task progress, so they are
    asserted against the catalogue in the tests.
    """

    LOGIN = "LOGIN"
    MOVE = "MOVE"
    RULE_CAST = "RULE_CAST"


class InvalidLevelEvent(ValueError):
    """The event cannot be published and must not advance anything."""


# GDD 13.2 lists the only three reasons allowed to write leaderboard score.
# Room gameplay events are deliberately absent: a move is not worth points, and
# a rule cast pays out through the discovery or settlement it causes, not by
# itself. This constant exists so the rule is stated once and asserted in tests
# rather than living in a comment nobody checks.
SCORE_EVENT_REASONS = frozenset({"EXP_DISCOVER", "CLEAR_STAGE", "COLLECT_NEW"})


@dataclass(frozen=True)
class LevelEvent:
    type: LevelEventType
    player_id: UUID
    source_id: str
    run_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.type, LevelEventType):
            raise InvalidLevelEvent("event type must be a LevelEventType")
        if not isinstance(self.player_id, UUID):
            raise InvalidLevelEvent("player_id must be a UUID")
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise InvalidLevelEvent("source_id must be a non-empty string")
        if len(self.source_id) > MAX_SOURCE_ID_LENGTH:
            raise InvalidLevelEvent(
                f"source_id longer than {MAX_SOURCE_ID_LENGTH} characters"
            )
        if self.type in {LevelEventType.MOVE, LevelEventType.RULE_CAST}:
            if not isinstance(self.run_id, UUID):
                raise InvalidLevelEvent(f"{self.type} requires the level run it belongs to")
        if self.type is LevelEventType.LOGIN and self.run_id is not None:
            raise InvalidLevelEvent("LOGIN happens before a run exists")
        try:
            encoded = json.dumps(self.payload, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise InvalidLevelEvent("payload must be JSON serialisable") from error
        if len(encoded.encode("utf-8")) > MAX_PAYLOAD_BYTES:
            raise InvalidLevelEvent(
                f"payload larger than {MAX_PAYLOAD_BYTES} bytes"
            )

    @property
    def task_event_key(self) -> str:
        return f"{self.type.value}:{self.source_id}"

    def to_message(self) -> dict[str, Any]:
        return {
            "event": self.type.value,
            "source_id": self.source_id,
            "run_id": str(self.run_id) if self.run_id else None,
            "payload": self.payload,
        }


def login_event(player_id: UUID) -> LevelEvent:
    """One LOGIN per account.

    The tutorial objective asks the player to log in once, not once per day;
    using the account as the source id makes an innocent reinstall or a second
    device harmless.
    """
    return LevelEvent(type=LevelEventType.LOGIN, player_id=player_id, source_id="ACCOUNT")


def move_event(player_id: UUID, run_id: UUID, x: float, y: float) -> LevelEvent:
    """One MOVE per run.

    A player sends position updates several times a second. Keying on the run
    means the objective advances on the first accepted move of a run and every
    later packet is a no-op instead of flooding ``applied_events``.
    """
    return LevelEvent(
        type=LevelEventType.MOVE,
        player_id=player_id,
        run_id=run_id,
        source_id=f"RUN:{run_id}",
        payload={"x": round(float(x), 3), "y": round(float(y), 3)},
    )


def rule_cast_event(player_id: UUID, run_id: UUID, rule_id: str) -> LevelEvent:
    """One RULE_CAST per rule per run.

    Casting RULE_ECHO ten times is the same objective as casting it once, and
    the id stays stable across a retry of the same request.
    """
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise InvalidLevelEvent("rule_id must be a non-empty string")
    return LevelEvent(
        type=LevelEventType.RULE_CAST,
        player_id=player_id,
        run_id=run_id,
        source_id=f"RUN:{run_id}:RULE:{rule_id}",
        payload={"rule_id": rule_id},
    )
