from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LevelMovementSettings:
    movement_speed: float
    spawn_x: float
    spawn_y: float


def parse_level_movement_settings(config: dict[str, Any] | None) -> LevelMovementSettings:
    """Read the same movement speed and spawn point used by the Cocos client."""
    config = config or {}
    controls = config.get("prototype_controls")
    spawn = config.get("prototype_spawn")
    controls = {} if controls is None else controls
    spawn = {} if spawn is None else spawn
    if not isinstance(controls, dict) or not isinstance(spawn, dict):
        raise ValueError("level prototype movement settings must be objects")

    values = (
        controls.get("movement_speed", 3.0),
        spawn.get("x", 1.0),
        spawn.get("y", 4.0),
    )
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        for value in values
    ):
        raise ValueError(
            "level prototype movement speed and spawn coordinates must be finite numbers"
        )

    movement_speed, spawn_x, spawn_y = (float(value) for value in values)
    if movement_speed <= 0:
        raise ValueError("level prototype movement_speed must be positive")

    return LevelMovementSettings(
        movement_speed=movement_speed,
        spawn_x=spawn_x,
        spawn_y=spawn_y,
    )


def max_allowed_movement_distance(
    settings: LevelMovementSettings,
    elapsed_seconds: float,
    jitter_allowance: float = 0.75,
) -> float:
    if (
        isinstance(elapsed_seconds, bool)
        or not isinstance(elapsed_seconds, (int, float))
        or not math.isfinite(elapsed_seconds)
        or elapsed_seconds < 0
        or not math.isfinite(jitter_allowance)
        or jitter_allowance < 0
    ):
        raise ValueError(
            "movement elapsed time and jitter allowance must be finite and non-negative"
        )
    return settings.movement_speed * max(0.05, float(elapsed_seconds)) + jitter_allowance
