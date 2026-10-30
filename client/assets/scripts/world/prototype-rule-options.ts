import type { LawRuleId, RulePoint } from "../network/types";

export interface PrototypeMechanismPosition {
  position_x: number | null;
  position_y: number | null;
}

export interface PrototypeRuleOptions {
  targetId: string;
  targetPoint?: RulePoint;
}

/** RULE_ECHO is a point-radius cast; other laws target the mechanism directly. */
export function buildPrototypeRuleOptions(
  ruleId: LawRuleId,
  targetId: string,
  mechanism: PrototypeMechanismPosition | undefined
): PrototypeRuleOptions {
  if (ruleId !== "RULE_ECHO") return { targetId };

  if (
    !mechanism ||
    mechanism.position_x === null ||
    mechanism.position_y === null ||
    !Number.isFinite(mechanism.position_x) ||
    !Number.isFinite(mechanism.position_y)
  ) {
    throw new Error(`Cannot cast RULE_ECHO: mechanism coordinates are unavailable for ${targetId}`);
  }

  return {
    targetId,
    targetPoint: { x: mechanism.position_x, y: mechanism.position_y }
  };
}
