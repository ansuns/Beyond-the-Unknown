from app.modules.gameplay.service import (
    InvalidLawAction,
    _apply_single_rule,
    _combo_for_pair,
    _combo_is_allowed,
)


def test_preset_combo_order_rules(monkeypatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "law_combo_window_ms", 5_000)
    assert _combo_for_pair("RULE_ECHO", "RULE_GAZE", 1_000) == "COMBO-001"
    assert _combo_for_pair("RULE_GAZE", "RULE_ECHO", 1_000) is None
    assert _combo_for_pair("RULE_ECHO", "RULE_REVERSE", 1_000) == "COMBO-002"
    assert _combo_for_pair("RULE_REVERSE", "RULE_ECHO", 1_000) == "COMBO-002"
    assert _combo_for_pair("RULE_GAZE", "RULE_REVERSE", 1_000) == "COMBO-003"
    assert _combo_for_pair("RULE_REVERSE", "RULE_GAZE", 1_000) is None
    assert _combo_for_pair("RULE_ECHO", "RULE_GAZE", 5_001) is None
    assert _combo_for_pair("RULE_ECHO", "RULE_ECHO", 1_000) is None


def test_echo_reveals_personal_bridge_and_gaze_release_restores_state() -> None:
    state = {
        "state": "INVISIBLE",
        "base_state": "INVISIBLE",
        "active_rules": [],
        "revealed": False,
        "gaze_active": False,
        "reversed": False,
        "combo_completed": False,
        "combo_id": None,
        "version": 1,
        "config": {},
    }
    _apply_single_rule("PLATFORM_BRIDGE", state, "RULE_ECHO", "APPLY")
    assert state["state"] == "REVEALED"
    _apply_single_rule("PLATFORM_BRIDGE", state, "RULE_GAZE", "APPLY")
    assert state["gaze_active"] is True
    _apply_single_rule("PLATFORM_BRIDGE", state, "RULE_GAZE", "RELEASE")
    assert state["state"] == "INVISIBLE"
    assert state["gaze_active"] is False


def test_echo_rejects_incompatible_mechanism() -> None:
    state = {
        "state": "CLOSED",
        "base_state": "CLOSED",
        "active_rules": [],
        "revealed": False,
        "gaze_active": False,
        "reversed": False,
        "combo_completed": False,
        "combo_id": None,
        "version": 1,
        "config": {},
    }
    try:
        _apply_single_rule("DOOR_BARRIER", state, "RULE_ECHO", "APPLY")
    except InvalidLawAction:
        return
    raise AssertionError("Echo must reject unsupported mechanism types")


def test_combo_completed_mechanism_rejects_later_state_mutation() -> None:
    state = {
        "state": "OPEN",
        "base_state": "INVISIBLE",
        "active_rules": ["RULE_ECHO", "RULE_GAZE"],
        "revealed": True,
        "gaze_active": True,
        "reversed": False,
        "combo_completed": True,
        "combo_id": "COMBO-001",
        "version": 4,
        "config": {},
    }
    _apply_single_rule("PLATFORM_BRIDGE", state, "RULE_ECHO", "APPLY")
    _apply_single_rule("PLATFORM_BRIDGE", state, "RULE_GAZE", "RELEASE")
    assert state["state"] == "OPEN"
    assert state["gaze_active"] is True


def test_combo_requires_level_and_mechanism_configuration() -> None:
    level = {"required_combos": ["COMBO-001"]}
    mechanism_state = {"config": {"requires_combo": "COMBO-001"}}
    assert _combo_is_allowed(
        "COMBO-001", level, "PLATFORM_BRIDGE", mechanism_state
    )
    assert not _combo_is_allowed(
        "COMBO-001", level, "ENERGY_NODE", mechanism_state
    )
    assert not _combo_is_allowed(
        "COMBO-002", level, "ENERGY_NODE", mechanism_state
    )
    assert not _combo_is_allowed(
        "COMBO-001", {"required_combos": []}, "PLATFORM_BRIDGE", mechanism_state
    )
