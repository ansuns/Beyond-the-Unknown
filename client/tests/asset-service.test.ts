import { beforeEach, describe, expect, it, vi } from "vitest";

/**
 * Behavioural tests for the asset loader.
 *
 * These exist because the loader is the one place where "it looks fine" and
 * "it works" diverge: a broken retry shows up as a black screen on a train, a
 * missing in-flight guard downloads the same 760 KB twice, and a cached bundle
 * that never releases keeps every room's textures resident.
 */

type Callback = (error: Error | null, bundle: unknown) => void;

// hoisted so the vi.mock factory below can close over it: the factory runs
// before this module body executes.
const state = vi.hoisted(() => ({
  calls: 0,
  behaviours: [] as Array<(cb: (error: Error | null, bundle: unknown) => void) => void>,
  released: 0,
  removed: 0,
  version: "v1"
}));

vi.mock("cc", () => {
  class FakeAsset {}
  class FakeImageAsset extends FakeAsset {}
  const bundle = {
    config: { version: state.version },
    load: (path: string, _type: unknown, cb: (error: Error | null, asset: unknown) => void) =>
      path.includes("missing") ? cb(new Error("asset not found"), null) : cb(null, new FakeImageAsset()),
    releaseAll: () => {
      state.released += 1;
    }
  };
  return {
    Asset: FakeAsset,
    ImageAsset: FakeImageAsset,
    AssetManager: {},
    assetManager: {
      loadBundle: (_name: string, _options: unknown, callback: Callback) => {
        state.calls += 1;
        const behaviour = state.behaviours.shift();
        if (behaviour) behaviour(callback);
        else callback(null, bundle);
      },
      removeBundle: () => {
        state.removed += 1;
      }
    }
  };
});

import { AssetLoadError, assetService } from "../assets/scripts/engine/asset-service";
import { ASSET_CONFIG } from "../assets/scripts/engine/asset-config";

function reset(): void {
  // The service is a singleton; drop everything between tests so cache and
  // refcounts cannot leak into the next assertion.
  for (const name of assetService.stats().loaded) {
    assetService.release(name);
  }
  state.calls = 0;
  state.behaviours = [];
  state.released = 0;
  state.removed = 0;
  state.version = "v1";
  ASSET_CONFIG.remote.enabled = false;
  ASSET_CONFIG.bundles.resources.remote = false;
}

describe("asset service", () => {
  beforeEach(reset);

  it("reports progress while the bundle loads", async () => {
    const seen: number[] = [];
    state.behaviours = [
      (cb) => setTimeout(() => cb(null, undefined), 1),
      (cb) => setTimeout(() => cb(null, undefined), 1)
    ];
    await assetService.ensureBundle("resources", {
      onProgress: (percent) => seen.push(percent)
    });
    expect(seen.length).toBeGreaterThan(0);
    expect(seen.at(-1)).toBe(1);
  });

  it("caches a bundle instead of downloading it again", async () => {
    await assetService.ensureBundle("resources");
    await assetService.ensureBundle("resources");
    expect(state.calls).toBe(1);
  });

  it("de-duplicates concurrent requests for the same bundle", async () => {
    state.behaviours = [(cb) => setTimeout(() => cb(null, undefined), 5)];
    await Promise.all([
      assetService.ensureBundle("resources"),
      assetService.ensureBundle("resources"),
      assetService.ensureBundle("resources")
    ]);
    expect(state.calls).toBe(1);
  });

  it("retries a failed download and succeeds", async () => {
    state.behaviours = [
      (cb) => cb(new Error("network down")),
      (cb) => cb(null, undefined)
    ];
    await assetService.ensureBundle("resources", { retries: 1 });
    expect(state.calls).toBe(2);
  });

  it("gives up after the configured number of retries", async () => {
    state.behaviours = [
      (cb) => cb(new Error("down")),
      (cb) => cb(new Error("down")),
      (cb) => cb(new Error("down"))
    ];
    await expect(assetService.ensureBundle("resources", { retries: 2 })).rejects.toBeInstanceOf(
      AssetLoadError
    );
    expect(state.calls).toBe(3);
  });

  it("times out instead of hanging forever", async () => {
    // Never calls back, which is what a stalled socket looks like.
    state.behaviours = [() => undefined, () => undefined, () => undefined];
    await expect(
      assetService.ensureBundle("resources", { timeoutMs: 30, retries: 2 })
    ).rejects.toBeInstanceOf(AssetLoadError);
  });

  it("refuses a remote bundle whose version does not match", async () => {
    ASSET_CONFIG.remote.enabled = true;
    // The bundle must be declared remote, not just the CDN switched on.
    ASSET_CONFIG.bundles.resources.remote = true;
    ASSET_CONFIG.remote.baseUrl = "https://cdn.example.com/game";
    ASSET_CONFIG.remote.version = "v2";
    state.version = "v1";
    await expect(
      assetService.ensureBundle("resources", { retries: 0, timeoutMs: 500 })
    ).rejects.toBeInstanceOf(AssetLoadError);
  });

  it("releases a bundle only after the last reference is dropped", async () => {
    await assetService.ensureBundle("resources");
    assetService.retain("resources");
    assetService.retain("resources");
    expect(assetService.release("resources")).toBe(false);
    expect(assetService.release("resources")).toBe(false);
    expect(state.released).toBe(0);
    expect(assetService.release("resources")).toBe(true);
    expect(state.released).toBe(1);
    expect(state.removed).toBe(1);
    expect(assetService.isLoaded("resources")).toBe(false);
  });

  it("loads an asset out of the bundle", async () => {
    const asset = await assetService.loadImage("resources", "maps/x/scene/y");
    expect(asset).not.toBeNull();
  });

  it("returns null rather than throwing when an asset is missing", async () => {
    const asset = await assetService.load("resources", "missing", class {} as never, {
      retries: 0
    });
    expect(asset).toBeNull();
  });
});
