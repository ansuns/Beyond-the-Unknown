// Deciding how big the game's design resolution should be.
//
// The design resolution used to be a constant: 960x640 in the project settings.
// With that constant the engine scales by a single factor, and the visible area
// only matches the screen when the screen happens to be 3:2. On anything else
// the HUD is laid out for a shape the player does not have - on an 844x390
// phone the visible height came out at 443 design units while the shell was
// written for 640 - so the page ends up cropped or padded.
//
// The design resolution is derived from the real viewport instead: one design
// unit is one CSS pixel, the visible size is the screen, and every layout that
// measures itself with view.getVisibleSize() fills the screen by construction.
//
// Kept free of engine imports so it can be unit tested; GameEntry passes in the
// platform objects it already holds.

export type ViewportMetrics = {
  width: number;
  height: number;
  /** Which source the numbers came from - recorded so a wrong size is traceable. */
  source: "wechat" | "browser";
};

type WeChatWindowInfo = {
  windowWidth?: number;
  windowHeight?: number;
  screenWidth?: number;
  screenHeight?: number;
};

/**
 * The subset of `globalThis` this module reads. Declared structurally so tests
 * can pass plain objects instead of faking a whole browser.
 */
export type ViewportHost = {
  wx?: {
    getWindowInfo?: () => WeChatWindowInfo;
    getSystemInfoSync?: () => WeChatWindowInfo;
  };
  innerWidth?: number;
  innerHeight?: number;
  visualViewport?: { width?: number; height?: number };
  screen?: { width?: number; height?: number };
};

/**
 * Below these sizes the numbers cannot be a real screen, so they are treated as
 * "not reported yet". Cocos builds the shell inside onLoad, and on WeChat and in
 * some browser embeddings the window metrics are still zero at that point;
 * adopting them would collapse the layout to nothing.
 */
export const MIN_USABLE_WIDTH = 240;
export const MIN_USABLE_HEIGHT = 160;

function positive(value: unknown, floor: number): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  if (value < floor) return undefined;
  return Math.round(value);
}

function fromPair(width: unknown, height: unknown): { width: number; height: number } | undefined {
  const w = positive(width, MIN_USABLE_WIDTH);
  const h = positive(height, MIN_USABLE_HEIGHT);
  if (w === undefined || h === undefined) return undefined;
  return { width: w, height: h };
}

function fromWeChat(host: ViewportHost): { width: number; height: number } | undefined {
  const wx = host.wx;
  if (!wx) return undefined;
  let info: WeChatWindowInfo | undefined;
  try {
    info = wx.getWindowInfo?.() ?? wx.getSystemInfoSync?.();
  } catch {
    // A base library without either call, or a throwing bridge.
    return undefined;
  }
  if (!info) return undefined;
  return fromPair(info.windowWidth, info.windowHeight);
}

/**
 * Reads the viewport in CSS pixels.
 *
 * WeChat first: its `window` shim does not always carry innerWidth, and the
 * mini game knows the true window size even when the browser shim does not.
 * Then the browser's layout viewport. `screen` is only a last resort because it
 * reports the physical display, which on desktop is much larger than the window
 * and on mobile ignores split-screen and browser chrome.
 */
export function readViewport(host: ViewportHost | undefined | null): ViewportMetrics | undefined {
  if (!host) return undefined;

  const wechat = fromWeChat(host);
  if (wechat) return { ...wechat, source: "wechat" };

  const browser = fromPair(host.innerWidth, host.innerHeight);
  if (browser) return { ...browser, source: "browser" };

  // visualViewport shrinks with the on-screen keyboard and pinch zoom, so it is
  // only used when innerWidth was missing entirely - never in preference to it.
  const visual = fromPair(host.visualViewport?.width, host.visualViewport?.height);
  if (visual) return { ...visual, source: "browser" };

  const screen = fromPair(host.screen?.width, host.screen?.height);
  if (screen) return { ...screen, source: "browser" };

  return undefined;
}

/**
 * The design resolution to install for a measured viewport.
 *
 * Returned essentially unchanged: one design unit per CSS pixel is what makes
 * the visible size equal the screen. The function exists to reject nonsense and
 * to keep the decision in one place.
 */
export function resolveDesignResolution(viewport: ViewportMetrics): {
  width: number;
  height: number;
} {
  return {
    width: Math.max(MIN_USABLE_WIDTH, Math.round(viewport.width)),
    height: Math.max(MIN_USABLE_HEIGHT, Math.round(viewport.height))
  };
}

/**
 * Whether a resize needs a new design resolution.
 *
 * Cocos forwards resizes for one-pixel changes (a scrollbar appearing, a mobile
 * URL bar sliding away). Refitting the shell for those would throw away the
 * room the player is standing in, so only real changes count.
 */
export function shouldRefit(
  current: { width: number; height: number },
  next: { width: number; height: number },
  tolerance = 2
): boolean {
  if (!Number.isFinite(next.width) || !Number.isFinite(next.height)) return false;
  if (next.width < MIN_USABLE_WIDTH || next.height < MIN_USABLE_HEIGHT) return false;
  return (
    Math.abs(next.width - current.width) > tolerance ||
    Math.abs(next.height - current.height) > tolerance
  );
}
