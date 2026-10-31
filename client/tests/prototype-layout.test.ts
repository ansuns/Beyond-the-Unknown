import { describe, expect, it } from "vitest";

import {
  calculatePrototypeRoomScale,
  parsePrototypeLayoutConfig,
  prototypeLevelToLocal,
  prototypeLocalToLevel,
  screenDirectionToLogicalDirection
} from "../assets/scripts/world/prototype-layout";

describe("parsePrototypeLayoutConfig", () => {
  const validConfig = {
    prototype_bounds: { min_x: 0, max_x: 12, min_y: 0, max_y: 8 },
    prototype_spawn: { x: 1, y: 4 },
    prototype_controls: {
      movement_speed: 3,
      interaction_radius: 1.5,
      position_sync_interval_ms: 120
    }
  };

  it("maps server-owned layout and movement controls", () => {
    expect(parsePrototypeLayoutConfig(validConfig)).toEqual({
      bounds: { minX: 0, maxX: 12, minY: 0, maxY: 8 },
      spawn: { x: 1, y: 4 },
      movementSpeed: 3,
      interactionRadius: 1.5,
      positionSyncIntervalMs: 120
    });
  });

  it("rejects an out-of-bounds spawn", () => {
    expect(() => parsePrototypeLayoutConfig({
      ...validConfig,
      prototype_spawn: { x: 13, y: 4 }
    })).toThrow(/invalid values/);
  });

  it("rejects incomplete server control config", () => {
    expect(() => parsePrototypeLayoutConfig({
      ...validConfig,
      prototype_controls: { movement_speed: 3 }
    })).toThrow(/invalid values/);
  });
});

describe("isometric joystick direction", () => {
  it("maps screen cardinal directions into normalized logical directions", () => {
    const up = screenDirectionToLogicalDirection({ x: 0, y: 1 });
    expect(up.x).toBeCloseTo(Math.SQRT1_2);
    expect(up.y).toBeCloseTo(Math.SQRT1_2);
    const right = screenDirectionToLogicalDirection({ x: 1, y: 0 });
    expect(right.x).toBeCloseTo(Math.SQRT1_2);
    expect(right.y).toBeCloseTo(-Math.SQRT1_2);
  });

  it("returns zero for a centered stick and rejects non-finite input", () => {
    expect(screenDirectionToLogicalDirection({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
    expect(() => screenDirectionToLogicalDirection({ x: Number.NaN, y: 0 })).toThrow(/finite/);
  });
});

describe("prototype layout coordinate contract", () => {
  const bounds = { minX: 10, maxX: 22, minY: -4, maxY: 4 };

  it("projects all four logical corners to a diamond and round-trips them", () => {
    const scale = 20;
    const corners = [
      [{ x: 10, y: -4 }, { x: -40, y: -200 }],
      [{ x: 22, y: -4 }, { x: 200, y: 40 }],
      [{ x: 22, y: 4 }, { x: 40, y: 200 }],
      [{ x: 10, y: 4 }, { x: -200, y: -40 }]
    ] as const;

    for (const [logical, projected] of corners) {
      expect(prototypeLevelToLocal(logical, bounds, scale)).toEqual(projected);
      expect(prototypeLocalToLevel(projected, bounds, scale)).toEqual(logical);
    }
  });

  it("clamps inverse-projected touch coordinates outside the diamond to logical bounds", () => {
    expect(prototypeLocalToLevel({ x: -999, y: 999 }, bounds, 20)).toEqual({
      x: 16,
      y: 4
    });
    expect(prototypeLocalToLevel({ x: -999, y: -999 }, bounds, 20)).toEqual({
      x: 10,
      y: 0
    });
  });

  it("fits the projected diamond to viewport while respecting the maximum scale", () => {
    expect(calculatePrototypeRoomScale(bounds, { width: 640, height: 600 })).toBe(18);
    expect(calculatePrototypeRoomScale(bounds, { width: 320, height: 400 })).toBe(8);
  });

  it("rejects invalid room scale and viewport geometry", () => {
    expect(() => prototypeLevelToLocal({ x: 10, y: -4 }, bounds, 0)).toThrow(/positive finite/);
    expect(() => calculatePrototypeRoomScale(
      { ...bounds, maxX: 10 },
      { width: 320, height: 400 }
    )).toThrow(/positive and finite/);
  });
});
