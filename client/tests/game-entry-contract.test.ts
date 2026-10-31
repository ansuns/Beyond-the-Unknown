import { describe, expect, it } from "vitest";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { findUndefinedThisCalls } from "../scripts/game-entry-contract.mjs";

describe("GameEntry member contract", () => {
  it("does not call undefined methods on the GameEntry instance", async () => {
    const source = await readFile(
      resolve(process.cwd(), "assets/scripts/engine/GameEntry.ts"),
      "utf8"
    );
    expect(findUndefinedThisCalls(source)).toEqual([]);
  });

  it("detects a missing instance method", () => {
    const source = `
      class BeyondTheUnknownGameEntry {
        onLoad() { this.missingUpdate(); }
      }
    `;
    expect(findUndefinedThisCalls(source, "GameEntry")).toEqual([
      "undefined this.missingUpdate() at line 3"
    ]);
  });

  it("allows inherited Cocos component methods and nested service calls", () => {
    const source = `
      class BeyondTheUnknownGameEntry {
        private api: any;
        onLoad() { this.schedule(() => this.api.login()); }
      }
    `;
    expect(findUndefinedThisCalls(source, "GameEntry")).toEqual([]);
  });
});
