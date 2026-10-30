import type {
  GazeMaintainData,
  GazeStopData,
  LawRuleId,
  LevelEnterData,
  LevelRunData,
  PersonalLevelState,
  RuleCastData,
  RuleCatalogData,
  RulePoint,
  SettlementData
} from "../network/types";
import type { RestClient } from "../network/rest-client";

export class PersonalLevelSession {
  private activeRunId?: string;

  constructor(private readonly api: RestClient) {}

  activeRun(): string | undefined {
    return this.activeRunId;
  }

  async enter(
    levelId: string,
    entranceId: string,
    idempotencyKey: string
  ): Promise<LevelEnterData> {
    const entry = await this.api.enterLevel(levelId, entranceId, idempotencyKey);
    this.activeRunId = entry.run_id;
    return entry;
  }

  async enterAndStart(
    levelId: string,
    entranceId: string,
    idempotencyKey: string
  ): Promise<{ entry: LevelEnterData; run: LevelRunData }> {
    const entry = await this.enter(levelId, entranceId, idempotencyKey);
    const run = await this.start();
    return { entry, run };
  }

  async start(): Promise<LevelRunData> {
    return this.api.startLevel(this.requireRun());
  }

  async abandon(): Promise<LevelRunData> {
    const run = await this.api.abandonLevel(this.requireRun());
    this.activeRunId = undefined;
    return run;
  }

  async settle(idempotencyKey: string): Promise<SettlementData> {
    const result = await this.api.settleLevel(this.requireRun(), idempotencyKey);
    if (result.result_status === "COMPLETED" || result.result_status === "FAILED") {
      this.activeRunId = undefined;
    }
    return result;
  }

  listRules(): Promise<RuleCatalogData> {
    return this.api.listRules();
  }

  castRule(
    ruleId: LawRuleId,
    options: { targetId?: string; targetPoint?: RulePoint },
    idempotencyKey: string
  ): Promise<RuleCastData> {
    return this.api.castRule(this.requireRun(), ruleId, options, idempotencyKey);
  }

  maintainGaze(targetId: string): Promise<GazeMaintainData> {
    return this.api.maintainGaze(this.requireRun(), targetId);
  }

  stopGaze(): Promise<GazeStopData> {
    return this.api.stopGaze(this.requireRun());
  }

  refreshState(): Promise<PersonalLevelState> {
    return this.api.getLevelState(this.requireRun());
  }

  private requireRun(): string {
    if (!this.activeRunId) {
      throw new Error("No active personal level run");
    }
    return this.activeRunId;
  }
}
