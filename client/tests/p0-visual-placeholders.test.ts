import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const [placeholderText, manifestText] = await Promise.all([
  readFile(resolve(process.cwd(), "assets/resources/P0-visual-placeholders.json"), "utf8"),
  readFile(resolve(process.cwd(), "../docs/engineering/assets/asset-manifest.v1.json"), "utf8")
]);
const placeholders = JSON.parse(placeholderText);
const manifest = JSON.parse(manifestText);

describe("P0 visual placeholder guard", () => {
  it("covers exactly the approved 25 visual IDs without claiming delivery", () => {
    expect(placeholders.assets).toHaveLength(25);
    expect(placeholders.counts).toEqual({
      logical_placeholders: 25,
      individual_visual_exports: 0,
      ready: 0
    });
    expect(placeholders.assets.every((asset: any) =>
      asset.placeholder_state === "PLACEHOLDER_ONLY" &&
      asset.runtime_loadable === false &&
      asset.visual_asset_delivered === false &&
      asset.manifest_status === "MISSING"
    )).toBe(true);
  });

  it("keeps placeholder definitions out of the authoritative asset file list", () => {
    for (const asset of placeholders.assets) {
      const entry = manifest.entries.find((item: any) => item.asset_id === asset.asset_id);
      expect(entry, `missing manifest entry for ${asset.asset_id}`).toBeTruthy();
      expect(entry.status).toBe("MISSING");
      expect(entry.files).not.toContain(asset.expected_directory + "/" + asset.asset_id + ".placeholder.json");
    }
    expect(manifest.status).toBe("BLOCKED_ASSETS_NOT_DELIVERED");
  });

  it("preserves the global projection, anchor, alpha, and logic authority contract", () => {
    expect(placeholders.global_contract).toMatchObject({
      style: "original_chibi_fantasy",
      projection: "45-degree-isometric",
      sprite_alpha: "real transparent channel required",
      character_anchor: "foot-contact-point",
      visual_logic_separation: true,
      server_logical_coordinates_are_authoritative: true
    });
  });

  it("defines all ROOM-01 mechanism states without taking over server logic", () => {
    const byId = new Map<string, any>(placeholders.assets.map((asset: any) => [asset.asset_id, asset]));
    expect(byId.get("M01-EXIT-01").contract.states).toEqual(["LOCKED", "UNLOCKABLE", "OPEN"]);
    expect(byId.get("M01-HIDEABLE-01").contract.states).toEqual(["HIDDEN", "ECHO_REVEALED", "REVEALED"]);
    expect(byId.get("M01-LIGHT-01").contract.states).toEqual(["INACTIVE", "ACTIVE"]);
    for (const id of ["M01-EXIT-01", "M01-HIDEABLE-01", "M01-LIGHT-01"]) {
      expect(byId.get(id).contract.logic_authority).toBe("server");
      expect(byId.get(id).contract.visual_only).toBe(true);
    }
  });
});
