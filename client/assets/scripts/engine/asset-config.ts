// @ts-nocheck
// Where each bundle comes from. Data, not logic, so switching a bundle between
// the package, a WeChat subpackage and a CDN is a one-line change and the
// loader never needs to know which it is.
//
// Current state: every bundle ships locally. The remote block exists, is wired
// into the loader including version checks, and is switched off, because there
// is no CDN for this project yet. Turning it on without a real server would
// only produce a convincing screenshot of a download that never happened.
//
// Two bundles:
//
// * `resources` - the built-in bundle. It only holds the art delivery contract
//   (P0-visual-placeholders.json), which is data for humans, not for the game.
// * `gameplay`  - a real Cocos Asset Bundle with compressionType "subpackage".
//   It carries every room / character / mechanism / effect sprite, none of
//   which is needed to draw the first frame. On WeChat it is emitted as a
//   native subpackage (game.json -> subpackages) and fetched on demand.
//
// The first screen must never depend on `gameplay`: the shell is drawn with
// Graphics + Label only, so the game is playable before the bundle arrives and
// a failed download degrades to placeholders instead of a black screen.

export type BundleEntry = {
  /** true = fetched from ASSET_CONFIG.remote.baseUrl instead of the package. */
  remote: boolean;
  /** Path under the CDN root; ignored when remote is false. */
  remotePath?: string;
  /** Shown in the loading overlay while this bundle downloads. */
  label: string;
};

export type BundleName = "resources" | "gameplay";

export const ASSET_CONFIG = {
  remote: {
    enabled: false,
    // Must be an HTTPS host that is registered in the mini program's
    // 服务器域名 before release; the platform blocks anything else.
    baseUrl: "",
    // Bumped per upload and written into the bundle config; the loader refuses
    // a mismatch instead of rendering old art with new code.
    version: ""
  },
  bundles: {
    resources: {
      remote: false,
      remotePath: "resources",
      label: "内置资源"
    },
    gameplay: {
      remote: false,
      remotePath: "gameplay",
      label: "场景资源"
    }
  } as Record<BundleName, BundleEntry>
};

/** Bundles that must be present before the first frame can be drawn. */
export const BOOT_BUNDLES: BundleName[] = [];
