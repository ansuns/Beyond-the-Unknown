import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { validateAssetManifestStructure } from "../scripts/asset-manifest-contract.mjs";

type AssetEntry = { asset_id: string; category: string; status: string; files: string[] };
type MutableManifest = Record<string, any> & { entries: AssetEntry[]; status: string };

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
    expect(manifest.entries.filter((entry: any) => entry.priority === "P0")).toHaveLength(37);
    expect(manifest.entries.filter((entry: any) => entry.priority === "P1")).toHaveLength(24);
    expect(manifest.entries.filter((entry: any) => entry.priority === "P2")).toHaveLength(51);
  });

  it("rejects an asset directory that does not match its canonical asset ID", () => {
    const invalid = structuredClone(manifest);
    invalid.entries.find((entry: { asset_id: string; expected_directory: string }) => entry.asset_id === "M01-HIDEABLE-01").expected_directory =
      "assets/resources/mechanisms/MEC_HIDEABLE";
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "M01-HIDEABLE-01: expected_directory must be assets/resources/mechanisms/M01-HIDEABLE-01"
    );
  });

  it("keeps the whole-GDD version separate from the Chapter 18 revision", () => {
    const invalid = { ...manifest, gdd_version: "0.1" };
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "asset manifest GDD baseline must be 0.2"
    );
    const staleChapter = { ...manifest, gdd_chapter_versions: { "18": "0.2" } };
    expect(validateAssetManifestStructure(staleChapter, levels).errors.join("\n")).toContain(
      "asset manifest Chapter 18 baseline must be 0.3"
    );
  });

  it("rejects a missing character asset entry", () => {
    const invalid = structuredClone(manifest) as MutableManifest;
    invalid.entries = invalid.entries.filter((entry: { asset_id: string }) => entry.asset_id !== "CHR_012_ANIMATION_SET");
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "required asset missing from manifest: CHR_012_ANIMATION_SET"
    );
  });

  it("rejects an orphan or miscategorized mechanism asset", () => {
    const invalid = structuredClone(manifest);
    const entry = invalid.entries.find((item: { asset_id: string; category: string }) => item.asset_id === "M03-ENERGY-01");
    entry.category = "effect";
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "M03-ENERGY-01: category must be mechanism, got effect"
    );
  });

  it("rejects file paths outside the declared asset directory", () => {
    const invalid = structuredClone(manifest);
    const entry = invalid.entries.find((item: { asset_id: string; status: string; files: string[] }) => item.asset_id === "CHR_001_PORTRAIT");
    entry.status = "READY";
    entry.files = ["assets/resources/ui/UI_LOGIN.png"];
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "file must be a safe path inside expected_directory"
    );
  });

  it("rejects reusing one file for multiple assets", () => {
    const invalid = structuredClone(manifest);
    invalid.entries[0].files = [
      "assets/resources/characters/CHR_001/portrait/portrait.png",
      "assets/resources/characters/CHR_001/portrait/portrait.png"
    ];
    invalid.entries[0].status = "IN_PROGRESS";
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

  it("rejects a delivery phase that does not match the asset priority", () => {
    const invalid = structuredClone(manifest);
    invalid.entries[0].delivery_phase = "CONTENT_EXPANSION";
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "CHR_001_PORTRAIT: delivery_phase must be VERTICAL_SLICE for priority P0"
    );
  });

  it("rejects an asset without a valid delivery priority", () => {
    const invalid = structuredClone(manifest);
    invalid.entries[0].priority = "P3";
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\n")).toContain(
      "CHR_001_PORTRAIT: priority must be P0, P1, or P2"
    );
  });


  it("rejects moving a critical ROOM-01 asset out of the P0 vertical slice", () => {
    const invalid = structuredClone(manifest);
    const entry = invalid.entries.find((item: { asset_id: string }) => item.asset_id === "M01-EXIT-01");
    entry.priority = "P1";
    entry.delivery_phase = "FIVE_ROOMS_AND_HIDDEN_ENDING";
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\\n")).toContain(
      "M01-EXIT-01: priority must be P0 per the approved production plan"
    );
  });

  it("rejects READY assets without provenance, license, and acceptance evidence", () => {
    const invalid = structuredClone(manifest);
    const entry = invalid.entries.find((item: { asset_id: string }) => item.asset_id === "CHR_001_PORTRAIT");
    entry.status = "READY";
    entry.files = ["assets/resources/characters/CHR_001/portrait/portrait.png"];
    const errors = validateAssetManifestStructure(invalid, levels).errors.join("\\n");
    expect(errors).toContain("CHR_001_PORTRAIT: READY requires provenance.source_type from the approved source types");
    expect(errors).toContain("CHR_001_PORTRAIT: READY requires non-empty provenance.source_reference");
    expect(errors).toContain("CHR_001_PORTRAIT: READY requires non-empty provenance.license");
    expect(errors).toContain("CHR_001_PORTRAIT: READY requires non-empty provenance.license_evidence");
    expect(errors).toContain("CHR_001_PORTRAIT: READY requires non-empty provenance.acceptance_evidence");
  });

  it("accepts READY asset provenance only when source, license, and acceptance evidence are recorded", () => {
    const valid = structuredClone(manifest);
    const entry = valid.entries.find((item: { asset_id: string }) => item.asset_id === "CHR_001_PORTRAIT");
    entry.status = "READY";
    entry.files = ["assets/resources/characters/CHR_001/portrait/portrait.png"];
    entry.provenance = {
      source_type: "ORIGINAL_INTERNAL",
      source_reference: "art-source/CHR_001/portrait-v1",
      license: "Owned original work",
      license_evidence: "docs/engineering/assets/evidence/CHR_001_PORTRAIT-license.md",
      acceptance_evidence: "docs/engineering/assets/evidence/CHR_001_PORTRAIT-acceptance.md"
    };
    expect(validateAssetManifestStructure(valid, levels).errors).toEqual([]);
  });

  it("rejects provenance evidence paths outside the controlled evidence directory", () => {
    const invalid = structuredClone(manifest);
    const entry = invalid.entries.find((item: { asset_id: string }) => item.asset_id === "CHR_001_PORTRAIT");
    entry.status = "READY";
    entry.files = ["assets/resources/characters/CHR_001/portrait/portrait.png"];
    entry.provenance = {
      source_type: "ORIGINAL_INTERNAL",
      source_reference: "art-source/CHR_001/portrait-v1",
      license: "Owned original work",
      license_evidence: "docs/engineering/assets/evidence/../../secrets.md",
      acceptance_evidence: "docs/engineering/assets/evidence/CHR_001_PORTRAIT-acceptance.md"
    };
    expect(validateAssetManifestStructure(invalid, levels).errors.join("\\n")).toContain(
      "CHR_001_PORTRAIT: provenance.license_evidence must be a safe Markdown path under docs/engineering/assets/evidence/"
    );
  });

});
