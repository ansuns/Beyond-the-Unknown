import { describe, expect, it } from "vitest";

import { buildPrototypeRuleOptions } from "../assets/scripts/world/prototype-rule-options";

describe("buildPrototypeRuleOptions", () => {
  it("supplies the server-authoritative mechanism point for RULE_ECHO", () => {
    expect(
      buildPrototypeRuleOptions("RULE_ECHO", "M05-BRIDGE-01", {
        position_x: 3,
        position_y: 4
      })
    ).toEqual({
      targetId: "M05-BRIDGE-01",
      targetPoint: { x: 3, y: 4 }
    });
  });

  it("does not add a point to object-targeted laws", () => {
    expect(
      buildPrototypeRuleOptions("RULE_GAZE", "M05-BRIDGE-01", {
        position_x: 3,
        position_y: 4
      })
    ).toEqual({ targetId: "M05-BRIDGE-01" });
  });

  it("rejects RULE_ECHO when the server did not provide usable coordinates", () => {
    expect(() =>
      buildPrototypeRuleOptions("RULE_ECHO", "M05-BRIDGE-01", {
        position_x: null,
        position_y: 4
      })
    ).toThrow(/coordinates are unavailable/);
  });
});
