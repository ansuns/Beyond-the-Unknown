export interface LevelProgressionCandidate {
  level_id: string;
  room_index: number | null;
  is_hidden: boolean;
  is_unlocked: boolean;
  repeatable: boolean;
}

/**
 * Selects the next normal room in order, then the unlocked hidden ending.
 * If all normal rooms are complete but the hidden route is still locked,
 * replay the final repeatable room so its hidden-route trigger can be retried.
 */
export function selectNextPlayableLevel<T extends LevelProgressionCandidate>(
  levels: readonly T[],
  completedLevelIds: readonly string[]
): T | undefined {
  const completed = new Set(completedLevelIds);
  const normal = levels
    .filter((level) => !level.is_hidden && level.is_unlocked)
    .slice()
    .sort((left, right) => (left.room_index ?? Number.MAX_SAFE_INTEGER) -
      (right.room_index ?? Number.MAX_SAFE_INTEGER));

  const nextIncomplete = normal.find((level) => !completed.has(level.level_id));
  if (nextIncomplete) return nextIncomplete;

  const hiddenEnding = levels.find((level) => level.is_hidden && level.is_unlocked);
  if (hiddenEnding) return hiddenEnding;

  return normal.filter((level) => level.repeatable).at(-1);
}
