import { describe, expect, it } from "vitest";

import { parsePrototypeLayoutConfig } from "../assets/scripts/world/prototype-layout";

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
