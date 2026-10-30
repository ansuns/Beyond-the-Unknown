import { describe, expect, it } from "vitest";
import { formatProgressSummary } from "../assets/scripts/ui/progress-summary";

describe("formatProgressSummary", () => {
  it("renders all progress counters and the weekly rank", () => {
    expect(
      formatProgressSummary({
        completedLevels: 3,
        discoveries: 8,
        collections: 5,
        pendingRewards: 2,
        worldArchiveRecords: 4,
        weeklyExploreRank: 7
      })
    ).toBe("通关 3  ·  发现 8  ·  收藏 5  ·  待领奖励 2  ·  世界档案 4  ·  周探索榜 #7");
  });

  it("distinguishes a player without a rank from an unavailable rank request", () => {
    expect(formatProgressSummary({ weeklyExploreRank: null })).toContain("周探索榜 未上榜");
    expect(formatProgressSummary({})).toContain("周探索榜 —");
  });
});
