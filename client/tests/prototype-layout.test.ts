import { describe, expect, it } from "vitest";

import {
  calculatePrototypeRoomScale,
  parsePrototypeLayoutConfig,
  prototypeLevelToLocal,
  prototypeLocalToLevel
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

describe("prototype layout coordinate contract", () => {
  const bounds = { minX: 10, maxX: 22, minY: -4, maxY: 4 };

  it("round-trips all room corners with non-zero coordinate origins", () => {
    const scale = 20;
    const min = prototypeLevelToLocal({ x: 10, y: -4 }, bounds, scale);
    const max = prototypeLevelToLocal({ x: 22, y: 4 }, bounds, scale);
    expect(min).toEqual({ x: -120, y: -80 });
    expect(max).toEqual({ x: 120, y: 80 });
    expect(prototypeLocalToLevel(min, bounds, scale)).toEqual({ x: 10, y: -4 });
    expect(prototypeLocalToLevel(max, bounds, scale)).toEqual({ x: 22, y: 4 });
  });

  it("clamps touch coordinates outside the room back to configured bounds", () => {
    expect(prototypeLocalToLevel({ x: -999, y: 999 }, bounds, 20)).toEqual({
      x: 10,
      y: 4
    });
  });

  it("fits the room to viewport while respecting the maximum scale", () => {
    expect(calculatePrototypeRoomScale(bounds, { width: 640, height: 600 })).toBe(40);
    expect(calculatePrototypeRoomScale(bounds, { width: 320, height: 400 })).toBeCloseTo(16);
  });

  it("rejects invalid room scale and viewport geometry", () => {
    expect(() => prototypeLevelToLocal({ x: 10, y: -4 }, bounds, 0)).toThrow(/positive finite/);
    expect(() => calculatePrototypeRoomScale(
      { ...bounds, maxX: 10 },
      { width: 320, height: 400 }
    )).toThrow(/positive and finite/);
  });
});
