import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { validateAssetManifestStructure } from "../scripts/asset-manifest-contract.mjs";

const [manifest, levels] = await Promise.all([
  readFile(resolve(process.cwd(), "../docs/engineering/assets/asset-manifest.v1.json"), "utf8"),
  readFile(resolve(process.cwd(), "../docs/engineering/levels/levels.v1.json"), "utf8")
]).then(([assetText, levelText]) => [JSON.parse(assetText), JSON.parse(levelText)]);

describe("asset manifest contract", () => {
  it("accepts the complete 112-entry manifest structure while assets are tracked as missing", () => {
    const result = validateAssetManifestStructure(manifest, levels);
    expect(result.errors).toEqual([]);
    expect(result.expectedCount).toBe(112);
    expect(result.counts.MISSING).toBe(112);
  });

  it("rejects a missing character asset entry", () => {
    const invalid = structuredClone(manifest);
    invalid.entries = invalid.entries.filter((entry) => entry.asset_id !== "CHR_012_ANIMATION_SET");
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "required asset missing from manifest: CHR_012_ANIMATION_SET"
    );
  });

  it("rejects an orphan or miscategorized mechanism asset", () => {
    const invalid = structuredClone(manifest);
    const entry = invalid.entries.find((item) => item.asset_id === "M03-ENERGY-01");
    entry.category = "effect";
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "M03-ENERGY-01: category must be mechanism, got effect"
    );
  });

  it("rejects file paths outside the declared asset directory", () => {
    const invalid = structuredClone(manifest);
    const entry = invalid.entries.find((item) => item.asset_id === "CHR_001_PORTRAIT");
    entry.status = "READY";
    entry.files = ["assets/resources/ui/UI_LOGIN.png"];
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "file must be a safe path inside expected_directory"
    );
  });

  it("rejects reusing one file for multiple assets", () => {
    const invalid = structuredClone(manifest);
    invalid.entries[0].files = ["assets/resources/characters/CHR_001/portrait/portrait.png"];
    invalid.entries[0].status = "IN_PROGRESS";
    invalid.entries[1].files = ["assets/resources/characters/CHR_001/portrait/portrait.png"];
    invalid.entries[1].status = "IN_PROGRESS";
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "file path is already assigned"
    );
  });

  it("rejects a false READY manifest and strict release with missing assets", () => {
    const invalid = structuredClone(manifest);
    invalid.status = "READY";
    const result = validateAssetManifestStructure(invalid, levels, true);
    expect(result.errors.join("\n")).toContain(
      "manifest cannot be READY while required entries are not all READY"
    );
    expect(result.errors.join("\n")).toContain("release blocker status=MISSING");
  });
});
