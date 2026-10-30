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


  it("sends personal law actions with bearer auth and an idempotency key", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      code: 0,
      message: "ok",
      request_id: "server-id",
      data: {
        run_id: "run-1",
        mechanism_id: "M02-BRIDGE-01",
        rule_id: "RULE_GAZE",
        action: "APPLY",
        state: { state: "OPEN", combo_completed: true },
        combo_id: "COMBO-001",
        idempotent_replay: false
      }
    }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl,
      requestId: () => "law-request"
    });

    const result = await api.applyLawAction(
      "run-1",
      "RULE_GAZE",
      "M02-BRIDGE-01",
      "APPLY",
      "law-action-0001"
    );
    expect(result.combo_id).toBe("COMBO-001");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://example.test/api/v1/level/law/action");
    const headers = init?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer jwt-token");
    expect(headers["Idempotency-Key"]).toBe("law-action-0001");
    expect(JSON.parse(String(init?.body))).toEqual({
      run_id: "run-1",
      rule_id: "RULE_GAZE",
      mechanism_id: "M02-BRIDGE-01",
      action: "APPLY"
    });
  });

  it("reads only the requested personal run mechanism endpoint", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({
      code: 0,
      message: "ok",
      request_id: "server-id",
      data: {
        run_id: "run-1",
        level_id: "LV-ROOM-01",
        status: "RUNNING",
        mechanisms: []
      }
    }), { status: 200 }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl
    });

    const result = await api.getRunMechanisms("run-1");
    expect(result.run_id).toBe("run-1");
    expect(fetchImpl.mock.calls[0][0]).toBe(
      "https://example.test/api/v1/level/runs/run-1/mechanisms"
    );
  });

});