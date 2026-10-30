import type { LawRuleId } from "../network/types";

export interface PrototypeComboDefinition {
  comboId: string;
  targetId: string;
  ruleIds: LawRuleId[];
  displayName: string;
}

const LAW_RULE_IDS = new Set<LawRuleId>([
  "RULE_ECHO",
  "RULE_GAZE",
  "RULE_REVERSE"
]);

/** Convert server level.config prototype_combos into validated client controls. */
export function parsePrototypeComboDefinitions(
  config: Record<string, unknown>
): PrototypeComboDefinition[] {
  const raw = config.prototype_combos;
  if (raw === undefined || raw === null) return [];
  if (!Array.isArray(raw)) {
    throw new Error("Level prototype_combos must be an array");
  }

  const seen = new Set<string>();
  return raw.map((value, index) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error(`Invalid prototype combo at index ${index}`);
    }
    const item = value as Record<string, unknown>;
    const comboId = item.combo_id;
    const targetId = item.target_mechanism_id;
    const displayName = item.display_name;
    const ruleSequence = item.rule_sequence;

    if (
      typeof comboId !== "string" ||
      !comboId.trim() ||
      seen.has(comboId) ||
      typeof targetId !== "string" ||
      !targetId.trim() ||
      typeof displayName !== "string" ||
      !displayName.trim() ||
      !Array.isArray(ruleSequence) ||
      ruleSequence.length !== 2 ||
      ruleSequence.some((rule) => typeof rule !== "string" || !LAW_RULE_IDS.has(rule as LawRuleId))
    ) {
      throw new Error(`Invalid prototype combo definition at index ${index}`);
    }

    seen.add(comboId);
    return {
      comboId,
      targetId,
      displayName,
      ruleIds: ruleSequence as LawRuleId[]
    };
  });
}
