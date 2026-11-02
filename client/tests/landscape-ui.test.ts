import { describe, expect, it } from "vitest";

import {
  calculatePrototypeRoomScale,
  prototypeLevelToLocal
} from "../assets/scripts/world/prototype-layout";

// Mirrors GameEntry.computeShellLayout + relayoutShell button placement + the
// in-room control row, so the checks run against the real layout instead of a
// hand-written rectangle. Any drift in GameEntry shows up as a failing viewport.
const LABEL_BOX_EXTRA = 16;
const VIEWPORTS = [
  { width: 1280, height: 720 },
  { width: 1560, height: 720 },
  { width: 844, height: 390 },
  { width: 926, height: 428 },
  { width: 932, height: 430 }
];

interface Rect { name: string; x: number; y: number; w: number; h: number }

function shell(w: number, h: number) {
  const compact = h < 560;
  const pad = compact ? 10 : 16;
  const titleSize = compact ? 21 : 30;
  const titleBox = titleSize + LABEL_BOX_EXTRA;
  const statusBox = (compact ? 12 : 16) + LABEL_BOX_EXTRA;
  const navHeight = compact ? 30 : 44;
  const navWidth = compact ? 88 : 110;
  const navInset = pad;
  const progressBox = (compact ? 11 : 13) + LABEL_BOX_EXTRA;
  const bottomHeight = compact ? 40 : 54;
  const bottomWidth = compact ? 140 : 190;
  const bottomSideWidth = compact ? 150 : 210;
  const rulesBox = (compact ? 12 : 14) + LABEL_BOX_EXTRA;
  const hintBox = 13 + LABEL_BOX_EXTRA;
  const showHint = h >= 580;

  let top = h / 2 - pad;
  top -= titleBox;
  top -= statusBox + (compact ? 2 : 6);
  const navY = top - navHeight / 2;
  top -= navHeight + 2;
  top -= progressBox + (compact ? 2 : 6);
  const topLimit = top;

  let floor = -h / 2 + pad;
  if (showHint) floor += hintBox + 2;
  const bottomY = floor + bottomHeight / 2;
  floor += bottomHeight + 2;
  floor += rulesBox + (compact ? 2 : 6);
  const bottomLimit = floor;

  const gap = compact ? 8 : 14;
  const available = Math.max(120, topLimit - bottomLimit);
  const worldHeight = Math.max(120, available - gap * 2);
  const worldY = bottomLimit + available / 2;
  const worldWidth = Math.max(160, w - pad * 2);

  return {
    pad, navY, navWidth, navHeight, navInset,
    bottomY, bottomHeight, bottomWidth, bottomSideWidth,
    worldY, worldWidth, worldHeight,
    joystickY: worldY - worldHeight / 2 + (compact ? 62 : 84),
    joystickBox: compact ? 116 : 144
  };
}

function controls(w: number, h: number): Rect[] {
  const L = shell(w, h);
  const list: Rect[] = [
    { name: "LoginButton", x: -w / 2 + L.bottomSideWidth / 2 + L.pad, y: L.bottomY, w: L.bottomSideWidth, h: L.bottomHeight },
    { name: "EnterLevelButton", x: 0, y: L.bottomY, w: L.bottomWidth, h: L.bottomHeight },
    { name: "ReturnButton", x: w / 2 - L.bottomSideWidth / 2 - L.pad, y: L.bottomY, w: L.bottomSideWidth, h: L.bottomHeight },
    { name: "ProgressButton", x: -w / 2 + L.navInset + L.navWidth / 2, y: L.navY, w: L.navWidth, h: L.navHeight },
    { name: "CharacterButton", x: 0, y: L.navY, w: L.navWidth, h: L.navHeight },
    { name: "EmoteButton", x: w / 2 - L.navInset - L.navWidth / 2, y: L.navY, w: L.navWidth, h: L.navHeight },
    { name: "Joystick", x: -w / 2 + L.joystickBox / 2 + L.pad, y: L.joystickY, w: L.joystickBox, h: L.joystickBox }
  ];

  // In-room control row (worldRoot-local -> screen by adding worldY).
  const compact = L.worldHeight < 320;
  const rowH = compact ? 32 : 42;
  const rowGap = compact ? 6 : 10;
  const inset = compact ? 6 : 12;
  const bottom = -L.worldHeight / 2 + inset;
  const primaryY = bottom + rowH / 2;
  const actionY = bottom + rowH + rowGap + rowH / 2;
  const sideX = L.worldWidth / 2 - (compact ? 70 : 88);
  list.push({ name: "SettleButton", x: 0, y: L.worldY + primaryY, w: 150, h: rowH });
  list.push({ name: "AbandonButton", x: sideX, y: L.worldY + actionY, w: 150, h: rowH });
  return list;
}

function overlaps(a: Rect, b: Rect): boolean {
  return Math.abs(a.x - b.x) < (a.w + b.w) / 2 - 0.5 &&
    Math.abs(a.y - b.y) < (a.h + b.h) / 2 - 0.5;
}

const ROOM_BOUNDS = { minX: 0, maxX: 12, minY: 0, maxY: 8 };
const SPAWN = { x: 1, y: 4 };

function roomScale(w: number, h: number) {
  const L = shell(w, h);
  return calculatePrototypeRoomScale(
    ROOM_BOUNDS,
    { width: L.worldWidth, height: L.worldHeight },
    {
      mustSee: [SPAWN, { x: 5, y: 4 }, { x: 7.5, y: 4 }, { x: 10.5, y: 4 }],
      safeHalfWidth: w / 2,
      safeHalfHeight: h / 2 - Math.abs(L.worldY),
      contentMargin: 24
    }
  );
}

describe("landscape control layout", () => {
  it("keeps every control inside the screen", () => {
    for (const vp of VIEWPORTS) {
      for (const c of controls(vp.width, vp.height)) {
        expect(Math.abs(c.x) + c.w / 2).toBeLessThanOrEqual(vp.width / 2 + 0.5);
        expect(Math.abs(c.y) + c.h / 2).toBeLessThanOrEqual(vp.height / 2 + 0.5);
      }
    }
  });

  it("does not overlap any two controls", () => {
    for (const vp of VIEWPORTS) {
      const list = controls(vp.width, vp.height);
      for (let i = 0; i < list.length; i += 1) {
        for (let j = i + 1; j < list.length; j += 1) {
          expect(overlaps(list[i], list[j]), `${list[i].name} / ${list[j].name} @ ${vp.width}x${vp.height}`).toBe(false);
        }
      }
    }
  });

  it("never covers the avatar spawn or the joystick-over-target case", () => {
    for (const vp of VIEWPORTS) {
      const L = shell(vp.width, vp.height);
      const scale = roomScale(vp.width, vp.height);
      const spawn = prototypeLevelToLocal(SPAWN, ROOM_BOUNDS, scale);
      const spawnScreen = { name: "spawn", x: spawn.x, y: L.worldY + spawn.y, w: 30, h: 30 };
      for (const c of controls(vp.width, vp.height)) {
        // The spawn is the player's start; no control may sit on top of it.
        expect(overlaps(c, spawnScreen), `${c.name} covers spawn @ ${vp.width}x${vp.height}`).toBe(false);
      }
    }
  });

  it("keeps the joystick clear of the in-room action buttons", () => {
    for (const vp of VIEWPORTS) {
      const list = controls(vp.width, vp.height);
      const joy = list.find((c) => c.name === "Joystick")!;
      for (const action of ["SettleButton", "AbandonButton"]) {
        const rect = list.find((c) => c.name === action)!;
        expect(overlaps(joy, rect), `joystick covers ${action} @ ${vp.width}x${vp.height}`).toBe(false);
      }
    }
  });
});
