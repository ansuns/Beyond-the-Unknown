import { describe, expect, it, vi } from "vitest";
import type { RestClient } from "../assets/scripts/network/rest-client";
import type { MapSession } from "../assets/scripts/world/map-session";
import type { PersonalLevelSession } from "../assets/scripts/world/personal-level-session";
import type { LawController } from "../assets/scripts/world/law-controller";
import { WorldPlaySession } from "../assets/scripts/world/world-play-session";

function makeWorldPlaySession(activeGaze = false) {
  const map = {
    enter: vi.fn().mockResolvedValue({
      map_id: "MAP_MAIN_001",
      instance_id: "instance-1",
      session_id: "session-1",
      spawn_position: { x: 0, y: 0, direction: "S" },
      current_players: 1,
      max_players: 20,
      reconnect_grace_seconds: 60,
      websocket_path: "/api/v1/ws/map"
    }),
    move: vi.fn(),
    action: vi.fn(),
    ping: vi.fn(),
    leave: vi.fn(),
    dispose: vi.fn()
  };
  const api = {
    getPlayerProfile: vi.fn().mockResolvedValue({
      player_id: "player-1",
      current_character_id: "CHR_001",
      progress_version: 0,
      status: "ACTIVE",
      created_at: "2026-10-01T00:00:00Z",
      updated_at: "2026-10-01T00:00:00Z"
    }),
    listCharacters: vi.fn().mockResolvedValue({
      current_character_id: "CHR_001",
      characters: []
    }),
    listLevels: vi.fn().mockResolvedValue({ levels: [] }),
    selectCharacter: vi.fn().mockResolvedValue({
      success: true,
      current_character_id: "CHR_002"
    })
  };
  const level = {
    enterAndStart: vi.fn().mockResolvedValue({
      entry: { run_id: "run-1" },
      run: { run_id: "run-1", status: "RUNNING" }
    }),
    abandon: vi.fn().mockResolvedValue({
      run_id: "run-1",
      status: "ABANDONED"
    })
  };
  const laws = {
    refreshCatalog: vi.fn().mockResolvedValue({ rules: [] }),
    refreshState: vi.fn().mockResolvedValue({
      run_id: "run-1",
      level_id: "LV-ROOM-01",
      mechanisms: []
    }),
    cast: vi.fn().mockResolvedValue({ run_id: "run-1", rule_id: "RULE_ECHO" }),
    maintainGazeIfDue: vi.fn().mockResolvedValue(undefined),
    hasActiveGaze: vi.fn().mockReturnValue(activeGaze),
    stopGaze: vi.fn().mockResolvedValue({ stopped: true })
  };
  const session = new WorldPlaySession(
    map as unknown as MapSession,
    api as unknown as RestClient,
    level as unknown as PersonalLevelSession,
    laws as unknown as LawController,
    () => "room-enter-0001"
  );
  return { session, map, api, level, laws };
}

describe("WorldPlaySession", () => {
  it("enters the shared map and loads authoritative player and character data", async () => {
    const { session, map, api } = makeWorldPlaySession();
    const onEvent = vi.fn();
    const result = await session.enterWorld(onEvent);

    expect(result.map.instance_id).toBe("instance-1");
    expect(result.profile.player_id).toBe("player-1");
    expect(result.characters.current_character_id).toBe("CHR_001");
    expect(map.enter).toHaveBeenCalledWith(onEvent, false);
    expect(api.getPlayerProfile).toHaveBeenCalledOnce();
    expect(api.listCharacters).toHaveBeenCalledOnce();
  });

  it("leaves the map if player bootstrap data cannot be loaded", async () => {
    const { session, map, api } = makeWorldPlaySession();
    api.listCharacters.mockRejectedValue(new Error("offline"));
    await expect(session.enterWorld(vi.fn())).rejects.toThrow("offline");
    expect(map.leave).toHaveBeenCalledOnce();
  });

  it("starts a personal room and loads its rule catalog and mechanism state", async () => {
    const { session, level, laws } = makeWorldPlaySession();
    const result = await session.enterRoom("LV-ROOM-01", "ENT-ROOM-01");

    expect(level.enterAndStart).toHaveBeenCalledWith(
      "LV-ROOM-01",
      "ENT-ROOM-01",
      "room-enter-0001"
    );
    expect(map.leave).toHaveBeenCalledOnce();
    expect(laws.refreshCatalog).toHaveBeenCalledOnce();
    expect(laws.refreshState).toHaveBeenCalledOnce();
    expect(result.run.status).toBe("RUNNING");
  });

  it("leaves the map when room startup fails after a run was created", async () => {
    const { session, map, level } = makeWorldPlaySession();
    level.activeRun = vi.fn().mockReturnValue("run-1");
    level.enterAndStart.mockRejectedValue(new Error("start failed"));
    await expect(session.enterRoom("LV-ROOM-01", "ENT-ROOM-01")).rejects.toThrow("start failed");
    expect(map.leave).toHaveBeenCalledOnce();
  });

  it("stops active gaze before abandoning a personal room", async () => {
    const { session, level, laws } = makeWorldPlaySession(true);
    await session.abandonRoom();
    expect(laws.stopGaze).toHaveBeenCalledOnce();
    expect(level.abandon).toHaveBeenCalledOnce();
    expect(laws.stopGaze.mock.invocationCallOrder[0]).toBeLessThan(
      level.abandon.mock.invocationCallOrder[0]
    );
  });

  it("delegates movement and actions to the shared-map session", () => {
    const { session, map } = makeWorldPlaySession();
    session.move(12, 18, "E", 42);
    session.action("ACT_001");
    session.ping();
    expect(map.move).toHaveBeenCalledWith(12, 18, "E", 42);
    expect(map.action).toHaveBeenCalledWith("ACT_001");
    expect(map.ping).toHaveBeenCalledOnce();
  });
});
