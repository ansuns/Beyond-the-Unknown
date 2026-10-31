import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { validateLevelContentConfig } from "../scripts/level-content-contract.mjs";

const config = JSON.parse(
  await readFile(resolve(process.cwd(), "../docs/engineering/levels/levels.v1.json"), "utf8")
);

describe("level content contract", () => {
  it("accepts the current five-room and hidden-ending prototype config", () => {
    expect(validateLevelContentConfig(config)).toEqual([]);
  });

  it("rejects hidden-route sequences that do not map to the corresponding ROOM-05 objectives", () => {
    const invalid = structuredClone(config);
    invalid.hidden_routes[0].trigger_mechanisms[0] = "M05-ENERGY-01";
    expect(validateLevelContentConfig(invalid).join("\n")).toContain(
      "sequence pair COMBO-001 -> M05-ENERGY-01 does not match ROOM-05 objective mapping"
    );
  });

  it("rejects an incomplete hidden-route combo/mechanism sequence", () => {
    const invalid = structuredClone(config);
    invalid.hidden_routes[0].trigger_mechanisms.pop();
    expect(validateLevelContentConfig(invalid).join("\n")).toContain(
      "trigger combo and mechanism sequences must have equal non-zero lengths"
    );
  });

  it("rejects a disabled MVP hidden route", () => {
    const invalid = structuredClone(config);
    invalid.hidden_routes[0].is_enabled = false;
    expect(validateLevelContentConfig(invalid).join("\n")).toContain(
      "MVP hidden route must be enabled"
    );
  });

  it("rejects duplicate entrance IDs and objective IDs across rooms", () => {
    const invalid = structuredClone(config);
    invalid.levels[1].entrance_id = invalid.levels[0].entrance_id;
    invalid.levels[1].necessary_objectives[0].objective_id =
      invalid.levels[0].necessary_objectives[0].objective_id;
    const errors = validateLevelContentConfig(invalid).join("\n");
    expect(errors).toContain("missing or duplicate entrance_id");
    expect(errors).toContain("missing or duplicate objective_id");
  });

  it("rejects objectives that reference undeclared combos", () => {
    const invalid = structuredClone(config);
    invalid.levels[4].necessary_objectives[0].required_combo = "COMBO-999";
    expect(validateLevelContentConfig(invalid).join("\n")).toContain(
      "references undeclared combo COMBO-999"
    );
  });

  it("rejects unknown or duplicated required laws", () => {
    const unknown = structuredClone(config);
    unknown.levels[0].required_laws = ["RULE_TIME"];
    expect(validateLevelContentConfig(unknown).join("\\n")).toContain("LV-ROOM-01: unknown required law RULE_TIME");
    const duplicate = structuredClone(config);
    duplicate.levels[0].required_laws = ["RULE_ECHO", "RULE_ECHO"];
    expect(validateLevelContentConfig(duplicate).join("\\n")).toContain("LV-ROOM-01: duplicate required_laws");
  });

  it("rejects invalid durations and incomplete mechanism state definitions", () => {
    const invalid = structuredClone(config);
    invalid.levels[0].estimated_duration_seconds = 0;
    delete invalid.levels[0].mechanisms[0].initial_state;
    const errors = validateLevelContentConfig(invalid).join("\\n");
    expect(errors).toContain("LV-ROOM-01: estimated_duration_seconds must be a positive integer");
    expect(errors).toContain("LV-ROOM-01: mechanism M01-HIDEABLE-01 requires initial_state");
  });

  it("rejects duplicate laws in a prototype combo sequence", () => {
    const invalid = structuredClone(config);
    invalid.levels[1].prototype_combos[0].rule_sequence = ["RULE_ECHO", "RULE_ECHO"];
    expect(validateLevelContentConfig(invalid).join("\\n")).toContain("LV-ROOM-02: prototype combo COMBO-001 must define exactly two known law rules");
  });

  it("rejects duplicate discovery IDs within a room", () => {
    const invalid = structuredClone(config);
    invalid.levels[0].discoveries = ["DIS_RULE_ECHO", "DIS_RULE_ECHO"];
    expect(validateLevelContentConfig(invalid).join("\\n")).toContain("LV-ROOM-01: duplicate discoveries");
  });
});
