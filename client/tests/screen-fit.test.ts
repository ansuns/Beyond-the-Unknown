import { describe, expect, it } from "vitest";

import {
  MIN_USABLE_HEIGHT,
  MIN_USABLE_WIDTH,
  readViewport,
  resolveDesignResolution,
  shouldRefit
} from "../assets/scripts/engine/screen-fit";

describe("readViewport", () => {
  it("prefers the WeChat window size, which is in CSS pixels", () => {
    const viewport = readViewport({
      wx: { getWindowInfo: () => ({ windowWidth: 844, windowHeight: 390 }) },
      innerWidth: 1280,
      innerHeight: 720
    });
    expect(viewport).toEqual({ width: 844, height: 390, source: "wechat" });
  });

  it("falls back to getSystemInfoSync on base libraries without getWindowInfo", () => {
    const viewport = readViewport({
      wx: { getSystemInfoSync: () => ({ windowWidth: 667, windowHeight: 375 }) }
    });
    expect(viewport).toEqual({ width: 667, height: 375, source: "wechat" });
  });

  it("ignores a throwing WeChat bridge instead of failing the boot", () => {
    const viewport = readViewport({
      wx: {
        getWindowInfo: () => {
          throw new Error("bridge not ready");
        }
      },
      innerWidth: 1024,
      innerHeight: 768
    });
    expect(viewport).toEqual({ width: 1024, height: 768, source: "browser" });
  });

  it("reads the browser layout viewport", () => {
    expect(readViewport({ innerWidth: 1560, innerHeight: 720 })).toEqual({
      width: 1560,
      height: 720,
      source: "browser"
    });
  });

  it("rejects zero and tiny sizes so the shell is never built for a 0x0 screen", () => {
    expect(readViewport({ innerWidth: 0, innerHeight: 0 })).toBeUndefined();
    expect(readViewport({ innerWidth: 120, innerHeight: 90 })).toBeUndefined();
    expect(readViewport({})).toBeUndefined();
    expect(readViewport(undefined)).toBeUndefined();
  });

  it("rejects a half-reported pair rather than guessing the missing axis", () => {
    expect(readViewport({ innerWidth: 1280 })).toBeUndefined();
  });

  it("only reaches for visualViewport when the layout viewport is missing", () => {
    expect(
      readViewport({ visualViewport: { width: 390, height: 844 } })
    ).toEqual({ width: 390, height: 844, source: "browser" });

    expect(
      readViewport({
        innerWidth: 1280,
        innerHeight: 720,
        visualViewport: { width: 390, height: 844 }
      })
    ).toEqual({ width: 1280, height: 720, source: "browser" });
  });
});

describe("resolveDesignResolution", () => {
  it("uses one design unit per CSS pixel", () => {
    expect(resolveDesignResolution({ width: 844, height: 390, source: "browser" })).toEqual({
      width: 844,
      height: 390
    });
  });

  it("rounds fractional sizes instead of producing a half-pixel canvas", () => {
    expect(resolveDesignResolution({ width: 844.6, height: 390.4, source: "browser" })).toEqual({
      width: 845,
      height: 390
    });
  });
});

describe("shouldRefit", () => {
  it("accepts a real size change", () => {
    expect(
      shouldRefit({ width: 1280, height: 720 }, { width: 844, height: 390 })
    ).toBe(true);
  });

  it("ignores the one-pixel churn that scrollbars and URL bars cause", () => {
    expect(
      shouldRefit({ width: 1280, height: 720 }, { width: 1281, height: 719 })
    ).toBe(false);
  });

  it("ignores nonsense rather than installing a broken design resolution", () => {
    expect(shouldRefit({ width: 1280, height: 720 }, { width: 0, height: 0 })).toBe(false);
    expect(
      shouldRefit({ width: 1280, height: 720 }, { width: Number.NaN, height: 720 })
    ).toBe(false);
    expect(
      shouldRefit({ width: MIN_USABLE_WIDTH, height: MIN_USABLE_HEIGHT }, {
        width: MIN_USABLE_WIDTH - 1,
        height: MIN_USABLE_HEIGHT - 1
      })
    ).toBe(false);
  });
});
