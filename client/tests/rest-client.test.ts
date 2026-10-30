import { describe, expect, it, vi } from "vitest";
import { ApiError, RestClient } from "../assets/scripts/network/rest-client";

describe("RestClient", () => {
  it("sends WeChat code and correlation headers without a bearer token", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      code: 0, message: "ok", request_id: "server-id",
      data: {
        access_token: "access", token_type: "Bearer", expires_in: 3600,
        player_id: "player-1", is_new_player: true, progress_version: 0, server_time: 1
      }
    }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => undefined,
      fetchImpl,
      requestId: () => "request-123"
    });

    const result = await api.login("temporary-wx-code");
    expect(result.access_token).toBe("access");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://example.test/api/v1/auth/login");
    expect((init?.headers as Record<string, string>).Authorization).toBeUndefined();
    expect((init?.headers as Record<string, string>)["X-Request-Id"]).toBe("request-123");
    expect(JSON.parse(String(init?.body))).toEqual({
      wx_code: "temporary-wx-code", request_id: "request-123"
    });
  });

  it("attaches the current bearer token to authenticated map entry", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      code: 0, message: "ok", request_id: "server-id",
      data: { map_id: "MAP_MAIN_001", instance_id: "instance", session_id: "session",
        spawn_position: { x: 0, y: 0, direction: "S" }, current_players: 1,
        max_players: 20, reconnect_grace_seconds: 60, websocket_path: "/api/v1/ws/map" }
    }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl,
      requestId: () => "request-456"
    });
    await api.enterMap();
    const [, init] = fetchImpl.mock.calls[0];
    expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer jwt-token");
  });

  it("maps non-success responses to ApiError", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Main map unavailable" }), { status: 503 })
    );
    const api = new RestClient({ baseUrl: "https://example.test/api/v1", fetchImpl });
    await expect(api.enterMap()).rejects.toBeInstanceOf(ApiError);
  });


  it("casts a rule through the authoritative API with target data and idempotency", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      code: 0,
      message: "ok",
      request_id: "server-id",
      data: {
        run_id: "run-1",
        rule_id: "RULE_ECHO",
        target_id: "MECH_BRIDGE",
        effects: [{ mechanism_id: "MECH_BRIDGE", state: { visible: true } }],
        combo: null,
        cooldown_until: "2026-10-30T14:00:05Z",
        idempotent_replay: false
      }
    }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl,
      requestId: () => "law-request"
    });

    const result = await api.castRule(
      "run-1",
      "RULE_ECHO",
      { targetId: "MECH_BRIDGE", targetPoint: { x: 1, y: 2 } },
      "law-cast-0001"
    );
    expect(result.effects[0].mechanism_id).toBe("MECH_BRIDGE");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://example.test/api/v1/level/rule/cast");
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer jwt-token");
    expect(headers["Idempotency-Key"]).toBe("law-cast-0001");
    expect(JSON.parse(String(init?.body))).toEqual({
      run_id: "run-1",
      rule_id: "RULE_ECHO",
      target_id: "MECH_BRIDGE",
      target_point: { x: 1, y: 2 }
    });
  });

  it("lists the server-owned rule catalog", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      code: 0,
      message: "ok",
      request_id: "server-id",
      data: { rules: [{ rule_id: "RULE_ECHO", is_unlocked: true, config_status: "TUNING_REQUIRED" }] }
    }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl
    });

    const result = await api.listRules();
    expect(result.rules[0].rule_id).toBe("RULE_ECHO");
    expect(fetchImpl.mock.calls[0][0]).toBe("https://example.test/api/v1/level/rules");
  });

  it("maintains and stops gaze using the backend's dedicated endpoints", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0, message: "ok", request_id: "r1",
        data: { run_id: "run-1", target_id: "MECH_BRIDGE", maintained_at: "2026-10-30T14:00:00Z" }
      }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        code: 0, message: "ok", request_id: "r2",
        data: { run_id: "run-1", stopped: true, target_id: "MECH_BRIDGE" }
      }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl
    });

    await api.maintainGaze("run-1", "MECH_BRIDGE");
    await api.stopGaze("run-1");
    expect(fetchImpl.mock.calls[0][0]).toBe("https://example.test/api/v1/level/rule/maintain");
    expect(JSON.parse(String(fetchImpl.mock.calls[0][1]?.body))).toEqual({
      run_id: "run-1", target_id: "MECH_BRIDGE"
    });
    expect(fetchImpl.mock.calls[1][0]).toBe("https://example.test/api/v1/level/rule/stop");
    expect(JSON.parse(String(fetchImpl.mock.calls[1][1]?.body))).toEqual({ run_id: "run-1" });
  });

  it("reads the authoritative state endpoint for one personal run", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      code: 0, message: "ok", request_id: "server-id",
      data: { run_id: "run-1", level_id: "LV-ROOM-01", mechanisms: [] }
    }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl
    });

    const result = await api.getLevelState("run-1");
    expect(result.run_id).toBe("run-1");
    expect(fetchImpl.mock.calls[0][0]).toBe("https://example.test/api/v1/level/state/run-1");
  });

  it("preserves structured cooldown details from the backend", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      detail: { code: "RULE_COOLDOWN", remaining_ms: 250 }
    }), { status: 409 }));
    const api = new RestClient({ baseUrl: "https://example.test/api/v1", fetchImpl });

    try {
      await api.listRules();
      throw new Error("Expected request to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).message).toBe("RULE_COOLDOWN");
      expect((error as ApiError).details).toEqual({ code: "RULE_COOLDOWN", remaining_ms: 250 });
    }
  });
});
