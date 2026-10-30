import { describe, expect, it, vi } from "vitest";
import { LawController, LawUnavailableError } from "../assets/scripts/world/law-controller";
import type { PersonalLevelSession } from "../assets/scripts/world/personal-level-session";
import type { RuleCatalogData } from "../assets/scripts/network/types";

function makeSession(catalog: RuleCatalogData) {
  return {
    listRules: vi.fn().mockResolvedValue(catalog),
    castRule: vi.fn().mockResolvedValue({ run_id: "run-1" }),
    maintainGaze: vi.fn().mockResolvedValue({ run_id: "run-1" }),
    stopGaze: vi.fn().mockResolvedValue({ run_id: "run-1", stopped: true }),
    refreshState: vi.fn().mockResolvedValue({ run_id: "run-1", level_id: "LV-ROOM-01", mechanisms: [] })
  } as unknown as PersonalLevelSession;
}

const catalog = (status: string, unlocked = true): RuleCatalogData => ({
  rules: [{
    rule_id: "RULE_ECHO",
    display_name: "回声",
    duration_type: "INSTANT",
    priority: 1,
    scope_type: "TARGET",
    cooldown_ms: null,
    radius: null,
    duration_ms: null,
    lease_timeout_ms: null,
    allowed_target_types: [],
    config_status: status,
    is_unlocked: unlocked
  }]
});

describe("LawController", () => {
  it("does not send casts before the server catalog is loaded", async () => {
    const session = makeSession(catalog("READY"));
    const controller = new LawController(session);
    expect(controller.availability("RULE_ECHO")).toEqual({
      ruleId: "RULE_ECHO",
      available: false,
      reason: "CATALOG_NOT_LOADED"
    });
    await expect(controller.cast("RULE_ECHO", {}, "echo-0001")).rejects.toMatchObject({
      name: "LawUnavailableError",
      reason: "CATALOG_NOT_LOADED"
    });
    expect(session.castRule).not.toHaveBeenCalled();
  });

  it("keeps laws visible but blocks casts while tuning is pending", async () => {
    const session = makeSession(catalog("TUNING_REQUIRED"));
    const controller = new LawController(session);
    await controller.refreshCatalog();
    expect(controller.availability("RULE_ECHO").reason).toBe("TUNING_REQUIRED");
    await expect(controller.cast("RULE_ECHO", {}, "echo-0001")).rejects.toBeInstanceOf(
      LawUnavailableError
    );
    expect(session.castRule).not.toHaveBeenCalled();
  });

  it("blocks a rule that is not unlocked", async () => {
    const session = makeSession(catalog("READY", false));
    const controller = new LawController(session);
    await controller.refreshCatalog();
    expect(controller.availability("RULE_ECHO").reason).toBe("RULE_LOCKED");
  });

  it("delegates a ready law to the server with the caller's idempotency key", async () => {
    const session = makeSession(catalog("READY"));
    const controller = new LawController(session);
    await controller.refreshCatalog();
    await controller.cast("RULE_ECHO", { targetId: "MECH_BRIDGE" }, "echo-0001");
    expect(session.castRule).toHaveBeenCalledWith(
      "RULE_ECHO",
      { targetId: "MECH_BRIDGE" },
      "echo-0001"
    );
  });

  it("allows stopping gaze even if the catalog has become unavailable", async () => {
    const session = makeSession(catalog("TUNING_REQUIRED"));
    const controller = new LawController(session);
    await controller.refreshCatalog();
    await controller.stopGaze();
    expect(session.stopGaze).toHaveBeenCalledOnce();
  });

  it("validates point and object target shapes before calling the backend", async () => {
    const pointCatalog = catalog("READY");
    pointCatalog.rules[0].scope_type = "POINT_RADIUS";
    const pointSession = makeSession(pointCatalog);
    const pointController = new LawController(pointSession);
    await pointController.refreshCatalog();
    await expect(
      pointController.cast("RULE_ECHO", {}, "echo-point-0001")
    ).rejects.toMatchObject({ name: "LawTargetError" });
    expect(pointSession.castRule).not.toHaveBeenCalled();

    const objectCatalog = catalog("READY");
    objectCatalog.rules[0].scope_type = "OBJECT_RADIUS";
    const objectSession = makeSession(objectCatalog);
    const objectController = new LawController(objectSession);
    await objectController.refreshCatalog();
    await expect(
      objectController.cast("RULE_ECHO", { targetPoint: { x: 0, y: 0 } }, "echo-object-0001")
    ).rejects.toMatchObject({ name: "LawTargetError" });
    expect(objectSession.castRule).not.toHaveBeenCalled();
  });

  it("renews a gaze lease at one-third of the server timeout and stops it", async () => {
    const ruleCatalog = catalog("READY");
    ruleCatalog.rules[0].rule_id = "RULE_GAZE";
    ruleCatalog.rules[0].scope_type = "OBJECT_RADIUS";
    ruleCatalog.rules[0].duration_type = "WHILE_CASTING";
    ruleCatalog.rules[0].lease_timeout_ms = 6000;
    const session = makeSession(ruleCatalog);
    let clock = 10_000;
    const controller = new LawController(session, () => clock);
    await controller.refreshCatalog();

    await controller.cast("RULE_GAZE", { targetId: "MECH_BRIDGE" }, "gaze-cast-0001");
    expect(await controller.maintainGazeIfDue()).toBeUndefined();

    clock += 2000;
    await controller.maintainGazeIfDue();
    expect(session.maintainGaze).toHaveBeenCalledTimes(1);

    clock += 1000;
    expect(await controller.maintainGazeIfDue()).toBeUndefined();
    clock += 1000;
    await controller.maintainGazeIfDue();
    expect(session.maintainGaze).toHaveBeenCalledTimes(2);

    await controller.stopGaze();
    clock += 10_000;
    expect(await controller.maintainGazeIfDue()).toBeUndefined();
    expect(session.stopGaze).toHaveBeenCalledOnce();
  });

  it("caches the latest authoritative personal mechanism state", async () => {
    const session = makeSession(catalog("READY"));
    const controller = new LawController(session);
    expect(controller.currentState()).toBeUndefined();
    const state = await controller.refreshState();
    expect(controller.currentState()).toEqual(state);
  });

});
