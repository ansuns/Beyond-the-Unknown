import { describe, expect, it } from "vitest";

import {
  calculatePrototypeRoomScale,
  parsePrototypeLayoutConfig,
  prototypeLevelToLocal,
  prototypeLocalToLevel,
  screenDirectionToLogicalDirection,
  sortIsometricDepth
} from "../assets/scripts/world/prototype-layout";

// Mirrors GameEntry.computeShellLayout for ROOM-01 so the geometry tests run
// against the real world band (the area the shell reserves between the title and
// the action rows), not a made-up viewport. Kept in sync with the constants in
// GameEntry.ts; a mismatch shows up as a failing acceptance viewport.
const LABEL_BOX_EXTRA = 16;
function shellMetrics(width: number, height: number) {
  const compact = height < 560;
  const pad = compact ? 10 : 16;
  const titleBox = (compact ? 21 : 30) + LABEL_BOX_EXTRA;
  const statusBox = (compact ? 12 : 16) + LABEL_BOX_EXTRA;
  const navHeight = compact ? 30 : 44;
  const progressBox = (compact ? 11 : 13) + LABEL_BOX_EXTRA;
  const bottomHeight = compact ? 40 : 54;
  const rulesBox = (compact ? 12 : 14) + LABEL_BOX_EXTRA;
  const hintBox = 13 + LABEL_BOX_EXTRA;
  const showHint = height >= 580;

  let top = height / 2 - pad;
  top -= titleBox;
  top -= statusBox + (compact ? 2 : 6);
  top -= navHeight + 2;
  top -= progressBox + (compact ? 2 : 6);
  const topLimit = top;

  let floor = -height / 2 + pad;
  if (showHint) floor += hintBox + 2;
  floor += bottomHeight + 2;
  floor += rulesBox + (compact ? 2 : 6);
  const bottomLimit = floor;

  const gap = compact ? 8 : 14;
  const available = Math.max(120, topLimit - bottomLimit);
  return {
    worldWidth: Math.max(160, width - pad * 2),
    worldHeight: Math.max(120, available - gap * 2),
    worldY: bottomLimit + available / 2
  };
}

// ROOM-01 server-owned geometry (migration 0011_room01_proto.py).
const ROOM_BOUNDS = { minX: 0, maxX: 12, minY: 0, maxY: 8 };
const ROOM_SPAWN = { x: 1, y: 4 };
const ROOM_MECHANISMS = [
  { x: 5, y: 4 },
  { x: 7.5, y: 4 },
  { x: 10.5, y: 4 }
];
const ACCEPTANCE_VIEWPORTS = [
  { width: 1280, height: 720 },
  { width: 1560, height: 720 },
  { width: 844, height: 390 },
  { width: 926, height: 428 },
  { width: 932, height: 430 }
];

/** Scale the running game would pick: cover, clamped so content stays visible. */
function roomScaleFor(width: number, height: number): number {
  const band = shellMetrics(width, height);
  return calculatePrototypeRoomScale(
    ROOM_BOUNDS,
    { width: band.worldWidth, height: band.worldHeight },
    {
      mustSee: [ROOM_SPAWN, ...ROOM_MECHANISMS],
      safeHalfWidth: width / 2,
      safeHalfHeight: height / 2 - Math.abs(band.worldY),
      contentMargin: 24
    }
  );
}

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

  it("covers the projected diamond to the viewport rather than fitting it", () => {
    // `size` is the world viewport, not the whole window: the shell has already
    // reserved space for the title, the action rows and the footer, so the only
    // margin left to subtract is the 24/48 px around the art. The room now
    // COVERS the viewport (reaches every edge, crops the longer axis) instead of
    // being fitted as a small centred square.
    const span = 12 + 8;
    const cover = (w: number, h: number) =>
      Math.min(220, (Math.max(Math.max(160, w - 48), Math.max(80, h - 24)) / span) * 1.06);

    expect(calculatePrototypeRoomScale(bounds, { width: 640, height: 600 }))
      .toBeCloseTo(cover(640, 600), 5);
    expect(calculatePrototypeRoomScale(bounds, { width: 320, height: 400 }))
      .toBeCloseTo(cover(320, 400), 5);
    // A wide phone is width-limited: the room square reaches both edges.
    const wide = calculatePrototypeRoomScale(bounds, { width: 1560, height: 720 });
    expect(wide * span).toBeGreaterThanOrEqual(1560 - 48);
    expect(wide * span).toBeGreaterThanOrEqual(720 - 24);
    // The hard ceiling still applies on a very large screen (4K+ width pushes
    // the cover value past 220, so the cap must clamp it back to 220).
    expect(calculatePrototypeRoomScale(bounds, { width: 6000, height: 3000 })).toBe(220);
  });

  it("projects a real diamond whose vertices fill the band on every acceptance viewport", () => {
    // The floor is an isometric diamond, not a rectangle. Assert against the four
    // projected vertices (the true edges), and against the band the shell actually
    // leaves free - not against the outer bounding square.
    const corners = [
      { x: 0, y: 0 },
      { x: 12, y: 0 },
      { x: 12, y: 8 },
      { x: 0, y: 8 }
    ];
    for (const vp of ACCEPTANCE_VIEWPORTS) {
      const band = shellMetrics(vp.width, vp.height);
      const scale = roomScaleFor(vp.width, vp.height);
      const projected = corners.map((c) => prototypeLevelToLocal(c, ROOM_BOUNDS, scale));
      const xs = projected.map((p) => p.x);
      const ys = projected.map((p) => p.y);
      const diamondWidth = Math.max(...xs) - Math.min(...xs);
      const diamondHeight = Math.max(...ys) - Math.min(...ys);

      // Reaches the top and bottom of the free band (the long axis is cropped).
      expect(diamondHeight).toBeGreaterThanOrEqual(band.worldHeight);
      // Covers the large majority of the band width; the full-screen environment
      // covers the remainder (no flat void, no tiny centred map).
      expect(diamondWidth).toBeGreaterThanOrEqual(band.worldWidth * 0.65);
    }
  });

  it("keeps the spawn and every mechanism inside the visible screen with margin", () => {
    for (const vp of ACCEPTANCE_VIEWPORTS) {
      const band = shellMetrics(vp.width, vp.height);
      const scale = roomScaleFor(vp.width, vp.height);
      const safeHalfWidth = vp.width / 2 - 24;
      const safeHalfHeight = vp.height / 2 - Math.abs(band.worldY) - 24;

      for (const point of [ROOM_SPAWN, ...ROOM_MECHANISMS]) {
        const projected = prototypeLevelToLocal(point, ROOM_BOUNDS, scale);
        // Inside the safe rect around the room centre.
        expect(Math.abs(projected.x)).toBeLessThanOrEqual(safeHalfWidth + 0.001);
        expect(Math.abs(projected.y)).toBeLessThanOrEqual(safeHalfHeight + 0.001);
        // And inside the real window once worldY is applied.
        const uiY = band.worldY + projected.y;
        expect(Math.abs(projected.x)).toBeLessThanOrEqual(vp.width / 2);
        expect(Math.abs(uiY)).toBeLessThanOrEqual(vp.height / 2);
      }
    }
  });

  it("would crop the spawn without the clamp (regression guard for the cover bug)", () => {
    // The pure cover scale pushes ROOM-01's spawn (x=1 -> unit offset -5) past
    // the screen edge on the 20:9 and compact viewports. This pins the reason the
    // clamp exists so a future "just use max()" change fails loudly.
    const scale = calculatePrototypeRoomScale(ROOM_BOUNDS, { width: 1528, height: 372 });
    const spawn = prototypeLevelToLocal(ROOM_SPAWN, ROOM_BOUNDS, scale);
    expect(Math.abs(spawn.y)).toBeGreaterThan(720 / 2); // off the 720px screen
  });

  it("rejects invalid room scale and viewport geometry", () => {
    expect(() => prototypeLevelToLocal({ x: 10, y: -4 }, bounds, 0)).toThrow(/positive finite/);
    expect(() => calculatePrototypeRoomScale(
      { ...bounds, maxX: 10 },
      { width: 320, height: 400 }
    )).toThrow(/positive and finite/);
  });
});

describe("landscape movement and interaction consistency", () => {
  it("keeps the on-screen move speed identical on every aspect ratio", () => {
    // GameEntry moves the avatar by (pxPerSecond / scale) level units and then
    // re-projects at the same scale, so the screen-space step must not change
    // when the viewport changes the zoom. (The sqrt(2) comes from the isometric
    // projection, not from the aspect ratio; the point is that it is constant.)
    const pxPerSecond = 150;
    const dt = 1 / 60;
    const steps = ACCEPTANCE_VIEWPORTS.map((vp) => {
      const scale = roomScaleFor(vp.width, vp.height);
      const start = prototypeLevelToLocal({ x: 6, y: 4 }, ROOM_BOUNDS, scale);
      const logicalStep = (pxPerSecond * dt) / scale;
      const end = prototypeLevelToLocal({ x: 6 + logicalStep, y: 4 }, ROOM_BOUNDS, scale);
      return Math.hypot(end.x - start.x, end.y - start.y);
    });
    for (const step of steps) {
      expect(step).toBeCloseTo(steps[0], 4);
    }
    expect(steps[0]).toBeCloseTo(pxPerSecond * dt * Math.SQRT2, 4);
  });

  it("round-trips the spawn and every mechanism through the inverse projection", () => {
    for (const vp of ACCEPTANCE_VIEWPORTS) {
      const scale = roomScaleFor(vp.width, vp.height);
      for (const point of [ROOM_SPAWN, ...ROOM_MECHANISMS]) {
        const projected = prototypeLevelToLocal(point, ROOM_BOUNDS, scale);
        const back = prototypeLocalToLevel(projected, ROOM_BOUNDS, scale);
        expect(back.x).toBeCloseTo(point.x, 4);
        expect(back.y).toBeCloseTo(point.y, 4);
      }
    }
  });

  it("maps a tap on a mechanism back to its logical cell (touch == position)", () => {
    for (const vp of ACCEPTANCE_VIEWPORTS) {
      const scale = roomScaleFor(vp.width, vp.height);
      for (const mechanism of ROOM_MECHANISMS) {
        const projected = prototypeLevelToLocal(mechanism, ROOM_BOUNDS, scale);
        const back = prototypeLocalToLevel(projected, ROOM_BOUNDS, scale);
        expect(Math.hypot(back.x - mechanism.x, back.y - mechanism.y)).toBeLessThan(0.01);
      }
    }
  });
});

describe("isometric depth sorting", () => {
  it("draws higher projected Y behind lower projected Y", () => {
    const ordered = sortIsometricDepth([
      { id: "front", screenY: -50 },
      { id: "back", screenY: 50 },
      { id: "middle", screenY: 0 }
    ]);
    expect(ordered.map((item) => item.id)).toEqual(["back", "middle", "front"]);
  });

  it("uses stable ID ordering for equal projected depth without mutating input", () => {
    const items = [
      { id: "zeta", screenY: 10 },
      { id: "alpha", screenY: 10 }
    ];
    expect(sortIsometricDepth(items).map((item) => item.id)).toEqual(["alpha", "zeta"]);
    expect(items.map((item) => item.id)).toEqual(["zeta", "alpha"]);
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
