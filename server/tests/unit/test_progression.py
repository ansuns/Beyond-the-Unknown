from datetime import UTC, datetime

from app.modules.progression.repository import _missing_objectives, _periods


def test_weekly_and_monthly_periods_use_server_timezone_and_utc() -> None:
    periods = _periods(datetime(2026, 10, 30, 12, 0, tzinfo=UTC))
    weekly, monthly = periods
    assert weekly["season_id"] == "W-2026-44"
    assert weekly["start"].isoformat() == "2026-10-26T00:00:00+00:00"
    assert weekly["end"].isoformat() == "2026-11-02T00:00:00+00:00"
    assert monthly["season_id"] == "M-2026-10"
    assert monthly["start"].isoformat() == "2026-10-01T00:00:00+00:00"
    assert monthly["end"].isoformat() == "2026-11-01T00:00:00+00:00"


def test_required_objectives_compare_only_server_mechanism_states() -> None:
    objectives = [
        {"objective_id": "A", "mechanism_id": "M1", "target_state": "REVEALED"},
        {"objective_id": "B", "mechanism_id": "M2", "target_state": "OPEN"},
    ]
    states = {
        "M1": {"status": "REVEALED"},
        "M2": {"status": "CLOSED"},
    }
    assert _missing_objectives(objectives, states) == ["B"]
    assert _missing_objectives(objectives, {}) == ["A", "B"]
    assert _missing_objectives(objectives, {
        "M1": {"status": "REVEALED"},
        "M2": {"status": "OPEN"},
    }) == []
