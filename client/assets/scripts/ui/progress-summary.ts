export interface ProgressSummarySnapshot {
  completedLevels?: number;
  discoveries?: number;
  collections?: number;
  pendingRewards?: number;
  worldArchiveRecords?: number;
  weeklyExploreRank?: number | null;
  weeklyClearRank?: number | null;
  weeklyCollectRank?: number | null;
}

function count(value: number | undefined): string {
  return value === undefined ? "—" : String(value);
}

function rank(value: number | null | undefined): string {
  if (value === undefined) return "—";
  return value === null ? "未上榜" : `#${value}`;
}

export function formatProgressSummary(snapshot: ProgressSummarySnapshot): string {
  return [
    `通关 ${count(snapshot.completedLevels)}`,
    `发现 ${count(snapshot.discoveries)}`,
    `收藏 ${count(snapshot.collections)}`,
    `待领奖励 ${count(snapshot.pendingRewards)}`,
    `世界档案 ${count(snapshot.worldArchiveRecords)}`,
    `周探索榜 ${rank(snapshot.weeklyExploreRank)}`,
    `周通关榜 ${rank(snapshot.weeklyClearRank)}`,
    `周收藏榜 ${rank(snapshot.weeklyCollectRank)}`
  ].join("  ·  ");
}
