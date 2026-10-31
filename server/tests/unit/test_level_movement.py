import pytest

from app.modules.levels.movement import parse_level_movement_settings


def test_parse_level_movement_settings_uses_server_owned_values() -> None:
    settings = parse_level_movement_settings(
        {
            "prototype_controls": {"movement_speed": 2.25},
            "prototype_spawn": {"x": 3.5, "y": 6.0},
        }
    )

    assert settings.movement_speed == 2.25
    assert settings.spawn_x == 3.5
    assert settings.spawn_y == 6.0


def test_parse_level_movement_settings_has_compatible_defaults() -> None:
    settings = parse_level_movement_settings(None)

    assert settings.movement_speed == 3.0
    assert settings.spawn_x == 1.0
    assert settings.spawn_y == 4.0


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True, "fast"])
def test_parse_level_movement_settings_rejects_invalid_speed(value: object) -> None:
    with pytest.raises(ValueError, match="movement"):
        parse_level_movement_settings({"prototype_controls": {"movement_speed": value}})


def test_parse_level_movement_settings_rejects_non_object_sections() -> None:
    with pytest.raises(ValueError, match="must be objects"):
        parse_level_movement_settings({"prototype_controls": []})
