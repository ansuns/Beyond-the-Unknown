import { describe, expect, it, vi } from "vitest";
import type { PersonalLevelSession } from "../assets/scripts/world/personal-level-session";
import {
  LawController,
  RuleTargetError,
  RuleUnavailableError
} from "../assets/scripts/world/law-controller";
import type {
  LawRuleId,
  PersonalLevelState,
  RuleCatalogData,
  RuleCastData
} from "../assets/scripts/network/types";

const state: PersonalLevelState = {
  run_id: "run-1",
  level_id: "LV-ROOM-02",
  mechanisms: []
};

function catalog(status: string = "READY"): RuleCatalogData {
  return {
    rules: [
      {
        rule_id: "RULE_ECHO",
        display_name: "回声",
        duration_type: "INSTANT",
        priority: 1,
        scope_type: "POINT_RADIUS",
        cooldown_ms: null,
        radius: 2,
        duration_ms: null,
        lease_timeout_ms: null,
        allowed_target_types: ["HIDDEN_OBJECT", "MECHANISM"],
        config_status: status,
        is_unlocked: true
      },
      {
        rule_id: "RULE_GAZE",
        display_name: "注视",
        duration_type: "WHILE_CASTING",
        priority: 2,
        scope_type: "OBJECT_RADIUS",
        cooldown_ms: null,
        radius: 2,
        duration_ms: null,
        lease_timeout_ms: 6000,
        allowed_target_types: ["PLATFORM", "MECHANISM"],
        config_status: status,
        is_unlocked: true
      },
      {
        rule_id: "RULE_REVERSE",
        display_name: "逆流",
        duration_type: "TIMED",
        priority: 3,
        scope_type: "OBJECT_RADIUS",
        cooldown_ms: null,
        radius: 2,
        duration_ms: 3000,
        lease_timeout_ms: null,
        allowed_target_types: ["ENERGY_NODE", "MOVING_OBJECT"],
        config_status: status,
        is_unlocked: true
      }
    ]
  };
}

function castResult(ruleId: LawRuleId): RuleCastData {
  return {
    run_id: "run-1",
    rule_id: ruleId,
    target_id: ruleId === "RULE_ECHO" ? null : "MECH_BRIDGE",
    effects: [],
    combo: null,
    cooldown_until: "2026-10-30T14:00:00Z",
    idempotent_replay: false
  };
}

function makeSession(status: string = "READY") {
  const session = {
    listRules: vi.fn(async () => catalog(status)),
    refreshState: vi.fn(async () => state),
    castRule: vi.fn(async (ruleId: LawRuleId) => castResult(ruleId)),
    maintainGaze: vi.fn(async (targetId: string) => ({
      run_id: "run-1",
      target_id: targetId,
      maintained_at: "2026-10-30T14:00:00Z"
    })),
    stopGaze: vi.fn(async () => ({
      run_id: "run-1",
      stopped: true,
      target_id: "MECH_BRIDGE"
    }))
  };
  return session as unknown as PersonalLevelSession & typeof session;
}

describe("LawController", () => {
  it("blocks casting while server tuning is not READY", async () => {
    const session = makeSession("TUNING_REQUIRED");
    const controller = new LawController(session, () => "law-action-0001");
    await controller.load();

    expect(controller.canCast("RULE_ECHO")).toBe(false);
    await expect(
      controller.cast("RULE_ECHO", { targetPoint: { x: 0, y: 0 } })
    ).rejects.toBeInstanceOf(RuleUnavailableError);
    expect(session.castRule).not.toHaveBeenCalled();
  });

  it("validates target shape before sending a rule cast", async () => {
    const session = makeSession();
    const controller = new LawController(session, () => "law-action-0002");
    await controller.load();

    await expect(controller.cast("RULE_ECHO", {})).rejects.toBeInstanceOf(RuleTargetError);
    expect(session.castRule).not.toHaveBeenCalled();

    const result = await controller.cast("RULE_ECHO", {
      targetPoint: { x: 0, y: 0 }
    });
    expect(result.rule_id).toBe("RULE_ECHO");
    expect(session.castRule).toHaveBeenCalledWith(
      "RULE_ECHO",
      { targetPoint: { x: 0, y: 0 } },
      "law-action-0002"
    );
  });

  it("maintains gaze at a bounded interval and stops the lease", async () => {
    const session = makeSession();
    let clock = 10_000;
    const controller = new LawController(
      session,
      () => "law-gaze-0001",
      () => clock
    );
    await controller.load();
    await controller.cast("RULE_GAZE", { targetId: "MECH_BRIDGE" });

    expect(await controller.maintainGazeIfDue()).toBeUndefined();
    clock += 2_000;
    expect((await controller.maintainGazeIfDue())?.target_id).toBe("MECH_BRIDGE");
    clock += 1_000;
    expect(await controller.maintainGazeIfDue()).toBeUndefined();
    clock += 1_000;
    expect((await controller.maintainGazeIfDue())?.target_id).toBe("MECH_BRIDGE");
    expect(session.maintainGaze).toHaveBeenCalledTimes(2);

    expect((await controller.stopGaze())?.stopped).toBe(true);
    expect(await controller.maintainGazeIfDue()).toBeUndefined();
    expect(session.stopGaze).toHaveBeenCalledTimes(1);
  });

  it("does not report locked rules as castable", async () => {
    const session = makeSession();
    const unlockedCatalog = catalog();
    unlockedCatalog.rules[2].is_unlocked = false;
    session.listRules.mockResolvedValue(unlockedCatalog);
    const controller = new LawController(session, () => "law-action-0003");
    await controller.load();

    expect(controller.canCast("RULE_REVERSE")).toBe(false);
    await expect(
      controller.cast("RULE_REVERSE", { targetId: "MECH_PLATFORM" })
    ).rejects.toBeInstanceOf(RuleUnavailableError);
  });
});
