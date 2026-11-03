// Pure helpers for enforcing the WeChat mini-game orientation.
//
// Cocos 3.8.8's headless wechatgame build writes `"deviceOrientation":
// "portrait"` into game.json regardless of `packages.wechatgame.orientation`
// in the build config or the CLI option (verified with a clean build). game.json
// is the authoritative runtime orientation, so the formal build flow must
// post-process it. This module holds the logic so it can be unit tested.

export const LANDSCAPE = "landscape";

/**
 * Return a copy of a game.json object with the landscape orientation enforced.
 * Preserves every other field and does not mutate the input.
 * @param {Record<string, unknown>} gameJson
 * @returns {Record<string, unknown>}
 */
export function ensureLandscape(gameJson) {
  if (!gameJson || typeof gameJson !== "object" || Array.isArray(gameJson)) {
    throw new Error("game.json must be an object");
  }
  return { ...gameJson, deviceOrientation: LANDSCAPE };
}

/** True when the object already declares landscape. */
export function isLandscape(gameJson) {
  return Boolean(gameJson) && gameJson.deviceOrientation === LANDSCAPE;
}
