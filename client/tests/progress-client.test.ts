import { describe, expect, it, vi } from "vitest";
import { RestClient } from "../assets/scripts/network/rest-client";

function response(data: unknown): Response {
  return new Response(JSON.stringify({
    code: 0,
    message: "ok",
    request_id: "progress-test",
    data
  }), { status: 200 });
}

describe("VS-5 progress API client", () => {
  it("settles only the active run ID and sends the idempotency key", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(response({
      result_id: "result-1",
      run_id: "run-1",
      level_id: "LV-ROOM-01",
      result_status: "COMPLETED",
      completion_time_ms: 12000,
      score_payload: { completed_objectives: ["EXIT_OPEN"] },
      unlocked_hidden_level_id: null,
      idempotent_replay: false
    }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl
    });

    const result = await api.settleLevel("run-1", "settle-run-1-0001");
    expect(result.result_status).toBe("COMPLETED");
    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://example.test/api/v1/level/settle");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ run_id: "run-1" });
    expect((init?.headers as Record<string, string>)["Idempotency-Key"])
      .toBe("settle-run-1-0001");
  });

  it("reads progress, codex, archive, rewards and claims a reward", async () => {
    const fetchImpl = vi.fn<typeof fetch>()
      .mockResolvedValueOnce(response({
        progress_version: 4,
        current_character_id: "CHR_001",
        completed_level_ids: ["LV-ROOM-01"],
        permanent_progress: {}
      }))
      .mockResolvedValueOnce(response({ discoveries: [] }))
      .mockResolvedValueOnce(response({ collections: [] }))
      .mockResolvedValueOnce(response({ records: [] }))
      .mockResolvedValueOnce(response({ pending: [], owned: [] }))
      .mockResolvedValueOnce(response({
        player_reward_id: "reward-player-1",
        reward_id: "REWARD-001",
        status: "OWNED",
        already_claimed: false
      }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl
    });

    expect((await api.getPlayerProgress()).progress_version).toBe(4);
    expect((await api.listPlayerDiscoveries()).discoveries).toEqual([]);
    expect((await api.listPlayerCollections()).collections).toEqual([]);
    expect((await api.listWorldArchive(200)).records).toEqual([]);
    expect((await api.listRewards()).pending).toEqual([]);
    expect((await api.claimReward("reward-player-1")).already_claimed).toBe(false);

    expect(fetchImpl.mock.calls.map(([url]) => String(url))).toEqual([
      "https://example.test/api/v1/player/progress",
      "https://example.test/api/v1/player/discoveries",
      "https://example.test/api/v1/player/collections",
      "https://example.test/api/v1/world/archive?limit=100",
      "https://example.test/api/v1/reward",
      "https://example.test/api/v1/reward/claim"
    ]);
    expect(JSON.parse(String(fetchImpl.mock.calls[5][1]?.body))).toEqual({
      player_reward_id: "reward-player-1"
    });
  });

  it("requests a typed weekly leaderboard and clamps the requested limit", async () => {
    const fetchImpl = vi.fn<typeof fetch>().mockResolvedValue(response({
      season_id: "WEEKLY-20261026",
      period_type: "WEEKLY",
      start_at_utc: "2026-10-26T00:00:00Z",
      end_at_utc: "2026-11-02T00:00:00Z",
      board_type: "EXPLORE",
      scope: "AROUND",
      entries: [],
      my_rank: null,
      is_snapshot: true
    }));
    const api = new RestClient({
      baseUrl: "https://example.test/api/v1",
      token: () => "jwt-token",
      fetchImpl
    });

    const result = await api.getLeaderboard("EXPLORE", "WEEKLY", "AROUND", 999);
    expect(result.is_snapshot).toBe(true);
    expect(fetchImpl.mock.calls[0][0]).toBe(
      "https://example.test/api/v1/leaderboard?board_type=EXPLORE&period_type=WEEKLY&scope=AROUND&limit=50"
    );
  });
});
