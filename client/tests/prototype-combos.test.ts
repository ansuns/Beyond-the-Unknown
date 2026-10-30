import { describe, expect, it } from "vitest";

import { parsePrototypeComboDefinitions } from "../assets/scripts/world/prototype-combos";

describe("parsePrototypeComboDefinitions", () => {
  it("maps server config to client controls without room-specific branching", () => {
    expect(parsePrototypeComboDefinitions({
      prototype_combos: [{
        combo_id: "COMBO-001",
        target_mechanism_id: "M05-BRIDGE-01",
        rule_sequence: ["RULE_ECHO", "RULE_GAZE"],
        display_name: "组合一·桥梁"
      }]
    })).toEqual([{
      comboId: "COMBO-001",
      targetId: "M05-BRIDGE-01",
      ruleIds: ["RULE_ECHO", "RULE_GAZE"],
      displayName: "组合一·桥梁"
    }]);
  });

  it("returns no controls for rooms without prototype combos", () => {
    expect(parsePrototypeComboDefinitions({ prototype_combos: [] })).toEqual([]);
  });

  it("fails closed for malformed or duplicate definitions", () => {
    expect(() => parsePrototypeComboDefinitions({
      prototype_combos: [{ combo_id: "COMBO-001" }]
    })).toThrow(/Invalid prototype combo/);
    expect(() => parsePrototypeComboDefinitions({
      prototype_combos: [
        { combo_id: "COMBO-001", target_mechanism_id: "M02-BRIDGE-01", rule_sequence: ["RULE_ECHO", "RULE_GAZE"], display_name: "A" },
        { combo_id: "COMBO-001", target_mechanism_id: "M02-BRIDGE-01", rule_sequence: ["RULE_ECHO", "RULE_GAZE"], display_name: "B" }
      ]
    })).toThrow(/Invalid prototype combo/);
  });
});
