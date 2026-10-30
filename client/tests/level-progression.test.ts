import { describe, expect, it } from "vitest";
import { selectNextPlayableLevel } from "../assets/scripts/world/level-progression";

const levels = [
  { level_id: "LV-ROOM-01", room_index: 1, is_hidden: false, is_unlocked: true, repeatable: true },
  { level_id: "LV-ROOM-02", room_index: 2, is_hidden: false, is_unlocked: true, repeatable: true },
  { level_id: "LV-ROOM-03", room_index: 3, is_hidden: false, is_unlocked: true, repeatable: true },
  { level_id: "LV-ROOM-04", room_index: 4, is_hidden: false, is_unlocked: true, repeatable: true },
  { level_id: "LV-ROOM-05", room_index: 5, is_hidden: false, is_unlocked: true, repeatable: true },
  { level_id: "LV-HIDDEN-01", room_index: null, is_hidden: true, is_unlocked: false, repeatable: false }
];

describe("level progression selection", () => {
  it("selects the first incomplete normal room instead of replaying room 1", () => {
    expect(selectNextPlayableLevel(levels, ["LV-ROOM-01"])?.level_id).toBe("LV-ROOM-02");
  });

  it("skips completed rooms even when the catalog marks all normal rooms unlocked", () => {
    expect(
      selectNextPlayableLevel(levels, ["LV-ROOM-01", "LV-ROOM-02", "LV-ROOM-03"])?.level_id
    ).toBe("LV-ROOM-04");
  });

  it("enters the hidden ending after all normal rooms are complete and the route is unlocked", () => {
    const unlocked = levels.map((level) =>
      level.level_id === "LV-HIDDEN-01" ? { ...level, is_unlocked: true } : level
    );
    expect(
      selectNextPlayableLevel(unlocked, [
        "LV-ROOM-01", "LV-ROOM-02", "LV-ROOM-03", "LV-ROOM-04", "LV-ROOM-05"
      ])?.level_id
    ).toBe("LV-HIDDEN-01");
  });

  it("replays ROOM-05 if all normal rooms are complete but the hidden route remains locked", () => {
    expect(
      selectNextPlayableLevel(levels, [
        "LV-ROOM-01", "LV-ROOM-02", "LV-ROOM-03", "LV-ROOM-04", "LV-ROOM-05"
      ])?.level_id
    ).toBe("LV-ROOM-05");
  });

  it("returns undefined when there is no unlocked level", () => {
    expect(selectNextPlayableLevel([], [])).toBeUndefined();
  });

  it("does not repeatedly enter a non-repeatable hidden ending after it is complete", () => {
    const unlockedAndCompleted = levels.map((level) =>
      level.level_id === "LV-HIDDEN-01" ? { ...level, is_unlocked: true } : level
    );
    expect(
      selectNextPlayableLevel(unlockedAndCompleted, [
        "LV-ROOM-01", "LV-ROOM-02", "LV-ROOM-03", "LV-ROOM-04",
        "LV-ROOM-05", "LV-HIDDEN-01"
      ])
    ).toBeUndefined();
  });
});
