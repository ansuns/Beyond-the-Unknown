// @ts-nocheck
// One place that knows how to fetch a bundle and its assets, so every caller
// gets the same timeout, retry, cache and release behaviour.
//
// The mini game has two very different sources:
//
// * a WeChat subpackage (local, shipped with the build) - loading is a file
//   read, but it still needs progress and a failure path;
// * a remote Asset Bundle (CDN) - needs a version check, a timeout and retries,
//   because the network is the one thing that will fail on a train.
//
// Callers must not care which one a bundle happens to be, so the decision is
// data in asset-config.ts and this module reads it.
import { Asset, AssetManager, assetManager, ImageAsset } from "cc";

import { ASSET_CONFIG, type BundleName } from "./asset-config";

export type ProgressReporter = (percent: number, note: string) => void;

export type LoadOptions = {
  timeoutMs?: number;
  retries?: number;
  onProgress?: ProgressReporter;
};

export class AssetLoadError extends Error {
  constructor(
    message: string,
    readonly bundle: string,
    readonly attempts: number
  ) {
    super(message);
    this.name = "AssetLoadError";
  }
}

const DEFAULT_TIMEOUT_MS = 12000;
const DEFAULT_RETRIES = 2;

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function withTimeout<T>(task: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      reject(new Error(`${label} timed out after ${timeoutMs}ms`));
    }, timeoutMs);
    task.then(
      (value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        reject(error);
      }
    );
  });
}

class AssetService {
  private readonly bundles = new Map<string, AssetManager.Bundle>();
  private readonly pending = new Map<string, Promise<AssetManager.Bundle>>();
  private readonly refCounts = new Map<string, number>();
  private readonly lastError = new Map<string, string>();

  /** Bundles that ship inside the package, so the name is enough. */
  private bundleLocation(name: string): { url?: string; remote: boolean } {
    const entry = ASSET_CONFIG.bundles[name as BundleName];
    if (!entry) return { remote: false };
    if (!entry.remote) return { remote: false };
    if (!ASSET_CONFIG.remote.enabled) {
      throw new AssetLoadError(
        `bundle "${name}" is configured as remote but remote loading is disabled`,
        name,
        0
      );
    }
    return {
      url: `${ASSET_CONFIG.remote.baseUrl}/${entry.remotePath}`.replace(/([^:])\/{2,}/g, "$1/"),
      remote: true
    };
  }

  isLoaded(name: string): boolean {
    return this.bundles.has(name);
  }

  /** Last failure for a bundle, for the diagnostics overlay. */
  errorOf(name: string): string | undefined {
    return this.lastError.get(name);
  }

  async ensureBundle(bundleName: string, options: LoadOptions = {}): Promise<AssetManager.Bundle> {
    const loaded = this.bundles.get(bundleName);
    if (loaded) {
      options.onProgress?.(1, `${bundleName} 已缓存`);
      return loaded;
    }
    const inFlight = this.pending.get(bundleName);
    if (inFlight) {
      // Two screens asking for the same bundle must share one download.
      return inFlight;
    }

    const location = this.bundleLocation(bundleName);
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const retries = options.retries ?? DEFAULT_RETRIES;

    const attempt = async (): Promise<AssetManager.Bundle> => {
      let lastFailure: Error | undefined;
      for (let index = 0; index <= retries; index += 1) {
        try {
          const bundle = await withTimeout(
            new Promise<AssetManager.Bundle>((resolve, reject) => {
              const onProgress = (finished: number, total: number) => {
                if (total <= 0) return;
                options.onProgress?.(Math.min(1, finished / total), `${bundleName} 下载中`);
              };
              const done = (error: Error | null, loadedBundle: AssetManager.Bundle) => {
                if (error) reject(error);
                else resolve(loadedBundle);
              };
              if (location.url) {
                assetManager.loadBundle(location.url, { onFileProgress: onProgress } as never, done);
              } else {
                assetManager.loadBundle(bundleName, { onFileProgress: onProgress } as never, done);
              }
            }),
            timeoutMs,
            `加载 ${bundleName}`
          );

          if (location.remote) {
            const expected = ASSET_CONFIG.remote.version;
            const actual = bundle.config?.version ?? "";
            if (expected && actual && expected !== actual) {
              // A stale CDN copy renders old art with new code; failing loudly
              // is the only honest option.
              throw new Error(
                `远程包 ${bundleName} 版本不匹配：期望 ${expected}，实际 ${actual}`
              );
            }
          }

          this.bundles.set(bundleName, bundle);
          this.refCounts.set(bundleName, 0);
          this.lastError.delete(bundleName);
          options.onProgress?.(1, `${bundleName} 就绪`);
          return bundle;
        } catch (error) {
          lastFailure = error instanceof Error ? error : new Error(String(error));
          this.lastError.set(bundleName, lastFailure.message);
          if (index < retries) {
            options.onProgress?.(0, `${bundleName} 第 ${index + 1} 次失败，重试中`);
            // Backoff keeps a broken CDN from being hammered by every client.
            await delay(400 * 2 ** index);
          }
        }
      }
      throw new AssetLoadError(
        lastFailure?.message ?? "unknown bundle failure",
        bundleName,
        retries + 1
      );
    };

    const promise = attempt().finally(() => {
      this.pending.delete(bundleName);
    });
    this.pending.set(bundleName, promise);
    return promise;
  }

  /** Load one asset out of a bundle, retrying the same way as the bundle. */
  async load<T extends Asset>(
    bundleName: string,
    path: string,
    type: new (...args: never[]) => T,
    options: LoadOptions = {}
  ): Promise<T | null> {
    const bundle = await this.ensureBundle(bundleName, options);
    const retries = options.retries ?? DEFAULT_RETRIES;
    const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    for (let index = 0; index <= retries; index += 1) {
      try {
        return await withTimeout(
          new Promise<T>((resolve, reject) => {
            bundle.load(path, type, (error: Error | null, asset: T) => {
              if (error) reject(error);
              else resolve(asset);
            });
          }),
          timeoutMs,
          `加载 ${bundleName}/${path}`
        );
      } catch (error) {
        this.lastError.set(bundleName, (error as Error).message);
        if (index < retries) await delay(300 * 2 ** index);
      }
    }
    return null;
  }

  async loadImage(bundleName: string, path: string, options: LoadOptions = {}): Promise<ImageAsset | null> {
    return this.load(bundleName, path, ImageAsset, options);
  }

  /** Take a reference so a scene change does not free a bundle still in use. */
  retain(bundleName: string): void {
    this.refCounts.set(bundleName, (this.refCounts.get(bundleName) ?? 0) + 1);
  }

  /**
   * Drop a reference; the bundle is released when the last holder lets go.
   *
   * Releasing the bundle frees its textures, which is the point: five rooms of
   * art held forever would defeat the split.
   */
  release(bundleName: string): boolean {
    const current = this.refCounts.get(bundleName) ?? 0;
    if (current > 0) {
      this.refCounts.set(bundleName, current - 1);
      return false;
    }
    const bundle = this.bundles.get(bundleName);
    if (!bundle) return false;
    bundle.releaseAll();
    assetManager.removeBundle(bundle);
    this.bundles.delete(bundleName);
    this.refCounts.delete(bundleName);
    return true;
  }

  stats(): { loaded: string[]; pending: string[]; errors: Record<string, string> } {
    return {
      loaded: [...this.bundles.keys()],
      pending: [...this.pending.keys()],
      errors: Object.fromEntries(this.lastError)
    };
  }
}

export const assetService = new AssetService();
