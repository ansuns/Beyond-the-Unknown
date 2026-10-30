import { describe, expect, it } from "vitest";
import { deriveRoom01VisualState } from "../assets/scripts/world/room01-presentation";

describe("ROOM-01 visual state", () => {
  it("keeps the hidden target concealed and exit locked before progression", () => {
    expect(deriveRoom01VisualState(new Map())).toEqual({
      hiddenTargetVisible: false,
      exitOpen: false
    });
  });

  it("reveals the hidden target from authoritative mechanism state", () => {
    expect(deriveRoom01VisualState(new Map([
      ["M01-HIDEABLE-01", { status: "ACTIVE", visible: true }],
      ["M01-EXIT-01", { status: "INACTIVE" }]
    ]))).toEqual({ hiddenTargetVisible: true, exitOpen: false });
  });

  it("opens the exit only after the server reports TRIGGERED", () => {
    expect(deriveRoom01VisualState(new Map([
      ["M01-HIDEABLE-01", { visible: true }],
      ["M01-EXIT-01", { status: "TRIGGERED" }]
    ]))).toEqual({ hiddenTargetVisible: true, exitOpen: true });
  });
});
