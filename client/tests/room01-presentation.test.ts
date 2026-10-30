import { describe, expect, it } from "vitest";
import { deriveRoom01VisualState } from "../assets/scripts/world/room01-presentation";

describe("ROOM-01 visual state", () => {
  it("keeps the hidden target concealed and exit locked before progression", () => {
    const state = deriveRoom01VisualState(new Map());
    expect(state).toEqual({ hiddenTargetVisible: false, exitOpen: false });
  });

  it("reveals the target only from the authoritative mechanism state", () => {
    const state = deriveRoom01VisualState(new Map([
      ["M01-HIDEABLE-01", { status: "ACTIVE", visible: true }],
      ["M01-EXIT-01", { status: "INACTIVE" }]
    ]));
    expect(state).toEqual({ hiddenTargetVisible: true, exitOpen: false });
  });

  it("shows the exit open only after the server reports TRIGGERED", () => {
    const state = deriveRoom01VisualState(new Map([
      ["M01-HIDEABLE-01", { visible: true }],
      ["M01-EXIT-01", { status: "TRIGGERED" }]
    ]));
    expect(state).toEqual({ hiddenTargetVisible: true, exitOpen: true });
  });
});
