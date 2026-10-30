import type {
  GazeMaintainData,
  GazeStopData,
  LawRuleId,
  PersonalLevelState,
  RuleCastData,
  RuleCatalogItem,
  RulePoint
} from "../network/types";
import type { PersonalLevelSession } from "./personal-level-session";

export class RuleUnavailableError extends Error {
  constructor(readonly ruleId: LawRuleId, readonly reason: "LOCKED" | "TUNING_REQUIRED") {
    super(reason === "LOCKED" ? `Rule ${ruleId} is not unlocked` : `Rule ${ruleId} is not ready`);
    this.name = "RuleUnavailableError";
  }
}

export class RuleTargetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "RuleTargetError";
  }
}

export interface RuleTarget {
  targetId?: string;
  targetPoint?: RulePoint;
}

export interface LawControllerSnapshot {
  rules: RuleCatalogItem[];
  state: PersonalLevelState;
}

export class LawController {
  private rules = new Map<LawRuleId, RuleCatalogItem>();
  private state?: PersonalLevelState;
  private gazeTargetId?: string;
  private lastGazeMaintainAt = 0;

  constructor(
    private readonly level: PersonalLevelSession,
    private readonly createIdempotencyKey: () => string,
    private readonly now: () => number = () => Date.now()
  ) {}

  async load(): Promise<LawControllerSnapshot> {
    const [catalog, state] = await Promise.all([
      this.level.listRules(),
      this.level.refreshState()
    ]);
    this.rules = new Map(catalog.rules.map((rule) => [rule.rule_id, rule]));
    this.state = state;
    return this.snapshot();
  }

  snapshot(): LawControllerSnapshot {
    if (!this.state) throw new Error("LawController has not been loaded");
    return { rules: [...this.rules.values()], state: this.state };
  }

  canCast(ruleId: LawRuleId): boolean {
    const rule = this.rules.get(ruleId);
    return Boolean(rule?.is_unlocked && rule.config_status === "READY");
  }

  async cast(ruleId: LawRuleId, target: RuleTarget): Promise<RuleCastData> {
    const rule = this.requireReadyRule(ruleId);
    this.validateTarget(rule, target);
    const result = await this.level.castRule(
      ruleId,
      target,
      this.createIdempotencyKey()
    );
    if (ruleId === "RULE_GAZE" && target.targetId) {
      this.gazeTargetId = target.targetId;
      this.lastGazeMaintainAt = 0;
    }
    this.state = await this.level.refreshState();
    return result;
  }

  async maintainGazeIfDue(): Promise<GazeMaintainData | undefined> {
    if (!this.gazeTargetId) return undefined;
    const rule = this.requireReadyRule("RULE_GAZE");
    const leaseTimeout = rule.lease_timeout_ms;
    if (!leaseTimeout || leaseTimeout <= 0) return undefined;
    const currentTime = this.now();
    const interval = Math.max(250, Math.floor(leaseTimeout / 3));
    if (currentTime - this.lastGazeMaintainAt < interval) return undefined;
    const result = await this.level.maintainGaze(this.gazeTargetId);
    this.lastGazeMaintainAt = currentTime;
    return result;
  }

  async stopGaze(): Promise<GazeStopData | undefined> {
    if (!this.gazeTargetId) return undefined;
    const result = await this.level.stopGaze();
    this.gazeTargetId = undefined;
    this.lastGazeMaintainAt = 0;
    this.state = await this.level.refreshState();
    return result;
  }

  async refresh(): Promise<PersonalLevelState> {
    this.state = await this.level.refreshState();
    return this.state;
  }

  private requireReadyRule(ruleId: LawRuleId): RuleCatalogItem {
    const rule = this.rules.get(ruleId);
    if (!rule?.is_unlocked) throw new RuleUnavailableError(ruleId, "LOCKED");
    if (rule.config_status !== "READY") {
      throw new RuleUnavailableError(ruleId, "TUNING_REQUIRED");
    }
    return rule;
  }

  private validateTarget(rule: RuleCatalogItem, target: RuleTarget): void {
    if (rule.scope_type === "POINT_RADIUS" && !target.targetPoint) {
      throw new RuleTargetError(`${rule.rule_id} requires a target point`);
    }
    if (rule.scope_type === "OBJECT_RADIUS" && !target.targetId) {
      throw new RuleTargetError(`${rule.rule_id} requires a target object`);
    }
    if (target.targetId && !rule.allowed_target_types.length) {
      throw new RuleTargetError(`${rule.rule_id} has no configured target types`);
    }
  }
}
