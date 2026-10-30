import type {
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

/**
 * Client-side orchestration only. The server remains authoritative for effects,
 * targets, cooldowns, combo matching and mechanism state.
 */
export class LawController {
  private catalog?: RuleCatalogData;

  constructor(private readonly session: PersonalLevelSession) {}

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
    this.assertAvailable(ruleId);
    return this.session.castRule(ruleId, options, idempotencyKey);
  }

  maintainGaze(targetId: string) {
    this.assertAvailable("RULE_GAZE");
    return this.session.maintainGaze(targetId);
  }

  stopGaze() {
    // Stopping an existing effect must remain possible even if catalog tuning
    // has since been disabled by the server.
    return this.session.stopGaze();
  }

  refreshState(): Promise<PersonalLevelState> {
    return this.session.refreshState();
  }

  private assertAvailable(ruleId: LawRuleId): void {
    const availability = this.availability(ruleId);
    if (!availability.available) {
      throw new LawUnavailableError(
        availability.reason ?? "RULE_NOT_FOUND",
        ruleId
      );
    }
  }
}
