import { describe, expect, it } from "vitest";

import {
  LANDSCAPE,
  ensureLandscape,
  isLandscape
} from "../scripts/wxgame-orientation.mjs";

describe("wechat game orientation", () => {
  it("forces portrait to landscape and preserves every other field", () => {
    const input = {
      deviceOrientation: "portrait",
      networkTimeout: { request: 5000, connectSocket: 5000 }
    };
    const output = ensureLandscape(input);
    expect(output.deviceOrientation).toBe(LANDSCAPE);
    expect(output.networkTimeout).toEqual({ request: 5000, connectSocket: 5000 });
    expect(input.deviceOrientation).toBe("portrait");
  });

  it("is idempotent on an already-landscape file", () => {
    const once = ensureLandscape({ deviceOrientation: "portrait" });
    const twice = ensureLandscape(once);
    expect(twice).toEqual(once);
    expect(isLandscape(twice)).toBe(true);
  });

  it("rejects values that are not objects", () => {
    expect(() => ensureLandscape(null as unknown as Record<string, unknown>)).toThrow(/object/);
    expect(() => ensureLandscape([] as unknown as Record<string, unknown>)).toThrow(/object/);
  });

  it("detects landscape and tolerates null", () => {
    expect(isLandscape({ deviceOrientation: LANDSCAPE })).toBe(true);
    expect(isLandscape({ deviceOrientation: "portrait" })).toBe(false);
    expect(isLandscape(null)).toBe(false);
  });
});
