"""Validation rules for the room event definitions (no database needed).

The tests exist because a malformed event is silent damage: it either advances
an objective it should not, or it drops an event the player earned. Each case
below is a way that could happen.
"""

from uuid import uuid4

import pytest

from app.modules.level_events.events import (
    MAX_SOURCE_ID_LENGTH,
    SCORE_EVENT_REASONS,
    InvalidLevelEvent,
    LevelEvent,
    LevelEventType,
    login_event,
    move_event,
    rule_cast_event,
)
from app.modules.progress.tasks import load_task_catalog


def test_event_values_match_the_task_catalogue() -> None:
    """The enum strings are the objective types; a rename would break progress."""
    catalogue_types = {
        objective["objective_type"]
        for task in load_task_catalog()
        for objective in task["objectives"]
    }
    assert {event.value for event in LevelEventType}.issubset(catalogue_types)


def test_room_events_are_not_score_reasons() -> None:
    """GDD 13.2 allows exactly three score reasons, none of them room events."""
    assert SCORE_EVENT_REASONS == {"EXP_DISCOVER", "CLEAR_STAGE", "COLLECT_NEW"}
    assert not ({event.value for event in LevelEventType} & SCORE_EVENT_REASONS)


def test_move_keys_on_the_run_so_packet_spam_cannot_recount() -> None:
    run_id = uuid4()
    player_id = uuid4()
    first = move_event(player_id, run_id, 1.0, 2.0)
    second = move_event(player_id, run_id, 5.0, 2.0)
    assert first.task_event_key == second.task_event_key
    assert first.task_event_key == f"MOVE:RUN:{run_id}"


def test_rule_cast_keys_on_rule_and_run_but_not_on_repetition() -> None:
    run_id = uuid4()
    player_id = uuid4()
    echo = rule_cast_event(player_id, run_id, "RULE_ECHO")
    echo_again = rule_cast_event(player_id, run_id, "RULE_ECHO")
    gaze = rule_cast_event(player_id, run_id, "RULE_GAZE")
    assert echo.task_event_key == echo_again.task_event_key
    assert echo.task_event_key != gaze.task_event_key


def test_login_keys_on_the_account_not_the_session() -> None:
    player_id = uuid4()
    assert login_event(player_id).task_event_key == "LOGIN:ACCOUNT"


def test_move_requires_its_run() -> None:
    with pytest.raises(InvalidLevelEvent, match="level run"):
        LevelEvent(
            type=LevelEventType.MOVE,
            player_id=uuid4(),
            source_id="RUN:1",
        )


def test_login_must_not_carry_a_run() -> None:
    with pytest.raises(InvalidLevelEvent, match="before a run"):
        LevelEvent(
            type=LevelEventType.LOGIN,
            player_id=uuid4(),
            source_id="ACCOUNT",
            run_id=uuid4(),
        )


@pytest.mark.parametrize("source_id", ["", "   ", "x" * (MAX_SOURCE_ID_LENGTH + 1)])
def test_source_id_must_be_usable_as_a_dedupe_key(source_id: str) -> None:
    with pytest.raises(InvalidLevelEvent, match="source_id"):
        LevelEvent(
            type=LevelEventType.LOGIN,
            player_id=uuid4(),
            source_id=source_id,
        )


def test_payload_must_be_json_serialisable() -> None:
    with pytest.raises(InvalidLevelEvent, match="JSON"):
        LevelEvent(
            type=LevelEventType.LOGIN,
            player_id=uuid4(),
            source_id="ACCOUNT",
            payload={"bad": object()},
        )


def test_payload_must_stay_small_enough_to_broadcast() -> None:
    with pytest.raises(InvalidLevelEvent, match="payload larger"):
        LevelEvent(
            type=LevelEventType.LOGIN,
            player_id=uuid4(),
            source_id="ACCOUNT",
            payload={"blob": "x" * 4096},
        )


def test_non_finite_positions_are_rejected() -> None:
    """NaN survives arithmetic and would poison the stored position."""
    with pytest.raises(InvalidLevelEvent, match="JSON"):
        move_event(uuid4(), uuid4(), float("nan"), 2.0)


def test_player_id_must_be_a_uuid() -> None:
    with pytest.raises(InvalidLevelEvent, match="player_id"):
        LevelEvent(
            type=LevelEventType.LOGIN,
            player_id="not-a-uuid",  # type: ignore[arg-type]
            source_id="ACCOUNT",
        )


def test_message_is_json_safe() -> None:
    import json

    run_id = uuid4()
    message = move_event(uuid4(), run_id, 3.25, 4.5).to_message()
    assert json.loads(json.dumps(message)) == {
        "event": "MOVE",
        "source_id": f"RUN:{run_id}",
        "run_id": str(run_id),
        "payload": {"x": 3.25, "y": 4.5},
    }
