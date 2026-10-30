import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

from app.modules.progress import repository as progress_repository


class _Mappings:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Result:
    def __init__(self, *, rows=None, values=None, scalar=None):
        self._rows = rows or []
        self._values = values or []
        self._scalar = scalar

    def mappings(self):
        return _Mappings(self._rows)

    def scalars(self):
        return _Scalars(self._values)

    def scalar_one_or_none(self):
        return self._scalar


def _route_fixture():
    return {
        "hidden_route_id": "HIDDEN-ROUTE-01",
        "prerequisite_levels": [
            "LV-ROOM-01",
            "LV-ROOM-02",
            "LV-ROOM-03",
            "LV-ROOM-04",
            "LV-ROOM-05",
        ],
        "trigger_level_id": "LV-ROOM-05",
        "trigger_combo_sequence": ["COMBO-001", "COMBO-002", "COMBO-003"],
        "trigger_mechanism_sequence": [
            "M05-BRIDGE-01",
            "M05-ENERGY-01",
            "M05-REVERSE-01",
        ],
        "result_level_id": "LV-HIDDEN-01",
    }


def _combo_rows(order):
    mechanism_by_combo = {
        "COMBO-001": "M05-BRIDGE-01",
        "COMBO-002": "M05-ENERGY-01",
        "COMBO-003": "M05-REVERSE-01",
    }
    return [
        {"combo_id": combo_id, "mechanism_id": mechanism_by_combo[combo_id]}
        for combo_id in order
    ]


def test_hidden_route_unlocks_for_canonical_room05_sequence(monkeypatch):
    player_id = uuid4()
    run_id = uuid4()
    session = AsyncMock()
    session.execute.side_effect = [
        _Result(rows=[_route_fixture()]),
        _Result(values=[
            "LV-ROOM-01",
            "LV-ROOM-02",
            "LV-ROOM-03",
            "LV-ROOM-04",
            "LV-ROOM-05",
        ]),
        _Result(values=[run_id]),
        _Result(rows=_combo_rows(["COMBO-001", "COMBO-002", "COMBO-003"])),
        _Result(scalar="HIDDEN-ROUTE-01"),
        _Result(),
    ]
    discovery_calls = []

    async def record_discovery(*args, **kwargs):
        discovery_calls.append((args, kwargs))
        return {"created": True}

    monkeypatch.setattr(progress_repository, "record_discovery", record_discovery)
    result = asyncio.run(progress_repository._try_unlock_hidden_route(session, player_id))

    assert result == {
        "hidden_route_id": "HIDDEN-ROUTE-01",
        "result_level_id": "LV-HIDDEN-01",
        "newly_unlocked": True,
    }
    assert session.execute.await_count == 6
    assert len(discovery_calls) == 1
    assert discovery_calls[0][0][2] == "DISC-HIDDEN-ROUTE-01"


def test_hidden_route_does_not_unlock_for_out_of_order_room05_combos(monkeypatch):
    player_id = uuid4()
    run_id = uuid4()
    session = AsyncMock()
    session.execute.side_effect = [
        _Result(rows=[_route_fixture()]),
        _Result(values=[
            "LV-ROOM-01",
            "LV-ROOM-02",
            "LV-ROOM-03",
            "LV-ROOM-04",
            "LV-ROOM-05",
        ]),
        _Result(values=[run_id]),
        _Result(rows=_combo_rows(["COMBO-002", "COMBO-001", "COMBO-003"])),
    ]

    result = asyncio.run(progress_repository._try_unlock_hidden_route(session, player_id))

    assert result is None
    assert session.execute.await_count == 4
