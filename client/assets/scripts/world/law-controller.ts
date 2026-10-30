import type {
  GazeMaintainData,
  GazeStopData,
  LawRuleId,
  PersonalLevelState,
  RuleCastData,
  RuleCatalogData,
  RulePoint
} from "../network/types";
import type { PersonalLevelSession } from "./personal-level-session";

export type LawUnavailableReason =
  | "CATALOG_NOT_LOADED"
  | "RULE_NOT_FOUND"
  | "RULE_LOCKED"
  | "TUNING_REQUIRED";

export interface LawAvailability {
  ruleId: LawRuleId;
  available: boolean;
  reason?: LawUnavailableReason;
}

export class LawUnavailableError extends Error {
  constructor(readonly reason: LawUnavailableReason, readonly ruleId: LawRuleId) {
    super(`Law ${ruleId} is unavailable: ${reason}`);
    this.name = "LawUnavailableError";
  }
}

export class LawTargetError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LawTargetError";
  }
}

/**
 * Client-side orchestration only. The server remains authoritative for effects,
 * targets, cooldowns, combo matching and mechanism state.
 */
export class LawController {
  private catalog?: RuleCatalogData;
  private state?: PersonalLevelState;
  private gazeTargetId?: string;
  private lastGazeMaintainAt = 0;

  constructor(
    private readonly session: PersonalLevelSession,
    private readonly now: () => number = () => Date.now()
  ) {}

  async refreshCatalog(): Promise<RuleCatalogData> {
    this.catalog = await this.session.listRules();
    return this.catalog;
  }

  availability(ruleId: LawRuleId): LawAvailability {
    if (!this.catalog) {
      return { ruleId, available: false, reason: "CATALOG_NOT_LOADED" };
    }
    const rule = this.catalog.rules.find((item) => item.rule_id === ruleId);
    if (!rule) return { ruleId, available: false, reason: "RULE_NOT_FOUND" };
    if (!rule.is_unlocked) return { ruleId, available: false, reason: "RULE_LOCKED" };
    if (rule.config_status !== "READY") {
      return { ruleId, available: false, reason: "TUNING_REQUIRED" };
    }
    return { ruleId, available: true };
  }

  async cast(
    ruleId: LawRuleId,
    options: { targetId?: string; targetPoint?: RulePoint },
    idempotencyKey: string
  ): Promise<RuleCastData> {
    const rule = this.assertAvailable(ruleId);
    this.validateTarget(rule.scope_type, ruleId, options);
    const result = await this.session.castRule(ruleId, options, idempotencyKey);
    if (ruleId === "RULE_GAZE" && options.targetId) {
      this.gazeTargetId = options.targetId;
      this.lastGazeMaintainAt = this.now();
    }
    return result;
  }

  maintainGaze(targetId: string): Promise<GazeMaintainData> {
    this.assertAvailable("RULE_GAZE");
    return this.session.maintainGaze(targetId).then((result) => {
      this.gazeTargetId = targetId;
      this.lastGazeMaintainAt = this.now();
      return result;
    });
  }

  /**
   * Call from the scene update loop. A lease is renewed at one-third of the
   * server-provided timeout, not once per rendered frame.
   */
  async maintainGazeIfDue(): Promise<GazeMaintainData | undefined> {
    if (!this.gazeTargetId || !this.catalog) return undefined;
    const rule = this.catalog.rules.find((item) => item.rule_id === "RULE_GAZE");
    const leaseTimeout = rule?.lease_timeout_ms;
    if (!leaseTimeout || leaseTimeout <= 0) return undefined;
    const currentTime = this.now();
    const interval = Math.max(250, Math.floor(leaseTimeout / 3));
    if (currentTime - this.lastGazeMaintainAt < interval) return undefined;
    const result = await this.session.maintainGaze(this.gazeTargetId);
    this.lastGazeMaintainAt = currentTime;
    return result;
  }

  hasActiveGaze(): boolean {\n    return this.gazeTargetId !== undefined;\n  }\n\n  async stopGaze(): Promise<GazeStopData> {
    // Stopping an existing effect must remain possible even if catalog tuning
    // has since been disabled by the server.
    const result = await this.session.stopGaze();
    this.gazeTargetId = undefined;
    this.lastGazeMaintainAt = 0;
    return result;
  }

  async refreshState(): Promise<PersonalLevelState> {
    this.state = await this.session.refreshState();
    return this.state;
  }

  currentState(): PersonalLevelState | undefined {
    return this.state;
  }

  private assertAvailable(ruleId: LawRuleId) {
    const availability = this.availability(ruleId);
    if (!availability.available) {
      throw new LawUnavailableError(
        availability.reason ?? "RULE_NOT_FOUND",
        ruleId
      );
    }
    return this.catalog!.rules.find((item) => item.rule_id === ruleId)!;
  }

  private validateTarget(
    scopeType: string,
    ruleId: LawRuleId,
    options: { targetId?: string; targetPoint?: RulePoint }
  ): void {
    if (scopeType === "POINT_RADIUS" && !options.targetPoint) {
      throw new LawTargetError(`${ruleId} requires a target point`);
    }
    if (scopeType === "OBJECT_RADIUS" && !options.targetId) {
      throw new LawTargetError(`${ruleId} requires a target object`);
    }
  }
}
