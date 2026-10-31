import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import {
  getPrototypeMechanismShape,
  getPrototypeMechanismVisualState
} from "../assets/scripts/world/prototype-mechanism-visual";

describe("prototype mechanism visual mapping", () => {
  it.each([
    ["PLATFORM_BRIDGE", "BRIDGE"],
    ["DOOR_BARRIER", "DOOR"],
    ["ENERGY_NODE", "ENERGY"],
    ["EXIT_GATE", "GATE"],
    ["HIDDEN_GATE", "GATE"],
    ["HIDEABLE", "HIDEABLE"],
    ["LIGHT_REVEAL", "ENERGY"],
    ["MOVING_OBJECT", "PLATFORM"],
    ["ENDING_CORE", "CORE"]
  ])("maps %s to the %s symbol", (mechanismType, expected) => {
    expect(getPrototypeMechanismShape(mechanismType)).toBe(expected);
  });

  it("uses a generic symbol for unknown future mechanism types", () => {
    expect(getPrototypeMechanismShape("FUTURE_MECHANISM")).toBe("GENERIC");
  });

  it.each(["TRIGGERED", "OPEN", "REVEALED", "REVERSED", "ENDPOINT_LOCKED", "ENDING_REVEALED"])(
    "marks %s as active",
    (status) => {
      expect(getPrototypeMechanismVisualState(status, false)).toBe("ACTIVE");
    }
  );

  it("lets an explicit visible flag override an otherwise inactive state", () => {
    expect(getPrototypeMechanismVisualState("INACTIVE", true)).toBe("ACTIVE");
  });

  it.each(["LOCKED", "SEALED", "CLOSED", "DORMANT", "INVISIBLE", "HIDDEN", "INACTIVE"])(
    "marks %s as locked",
    (status) => {
      expect(getPrototypeMechanismVisualState(status, false)).toBe("LOCKED");
    }
  );

  it("keeps unknown statuses neutral instead of falsely showing success", () => {
    expect(getPrototypeMechanismVisualState("UNRECOGNIZED", false)).toBe("IDLE");
  });

  it("provides a dedicated glyph for every mechanism type used by all six room configs", async () => {
    const config = JSON.parse(await readFile(
      resolve(process.cwd(), "../docs/engineering/levels/levels.v1.json"),
      "utf8"
    ));
    const configuredTypes = [...new Set(
      config.levels.flatMap((level: any) =>
        level.mechanisms.map((mechanism: any) => mechanism.mechanism_type)
      )
    )].sort();

    expect(configuredTypes.length).toBeGreaterThan(0);
    for (const mechanismType of configuredTypes) {
      expect(
        getPrototypeMechanismShape(mechanismType),
        `missing prototype glyph mapping for ${mechanismType}`
      ).not.toBe("GENERIC");
    }
  });

});
