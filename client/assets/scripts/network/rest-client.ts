import type {
  ApiEnvelope,
  CharacterCatalogData,
  CharacterSelectionData,
  GazeMaintainData,
  GazeStopData,
  LawRuleId,
  LevelCatalogData,
  LevelEnterData,
  LevelRunData,
  LoginData,
  MapEnterData,
  PersonalLevelState,
  PlayerProfile,
  RuleCastData,
  RuleCatalogData,
  RulePoint,
  PlayerProgressData,
  DiscoveryItem,
  CollectionItem,
  WorldArchiveItem,
  RewardInboxData,
  RewardClaimData,
  LeaderboardData,
  LeaderboardType,
  LeaderboardPeriod,
  LeaderboardScope,
  SettlementData
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: number,
    readonly requestId?: string,
    readonly details?: unknown
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface HttpResponseLike {
  status: number;
  ok: boolean;
  json(): Promise<unknown>;
}

export type FetchLike = (input: string | URL, init?: RequestInit) => Promise<HttpResponseLike>;

export interface RestClientOptions {
  baseUrl: string;
  token?: () => string | undefined;
  timeoutMs?: number;
  fetchImpl?: FetchLike;
  requestId?: () => string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export class RestClient {
  private readonly baseUrl: string;
  private readonly token: () => string | undefined;
  private readonly timeoutMs: number;
  private readonly fetchImpl: FetchLike;
  private readonly requestId: () => string;

  constructor(options: RestClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, "");
    this.token = options.token ?? (() => undefined);
    this.timeoutMs = options.timeoutMs ?? 10_000;
    this.fetchImpl = options.fetchImpl ?? fetch;
    this.requestId = options.requestId ?? (() => `client-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`);
  }

  async login(wxCode: string): Promise<LoginData> {
    const requestId = this.requestId();
    return this.request<LoginData>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ wx_code: wxCode, request_id: requestId }),
      authenticated: false,
      requestId
    });
  }

  async getPlayerProfile(): Promise<PlayerProfile> {
    return this.request<PlayerProfile>("/player/me", { method: "GET" });
  }

  async listCharacters(): Promise<CharacterCatalogData> {
    return this.request<CharacterCatalogData>("/player/characters", { method: "GET" });
  }

  async selectCharacter(characterId: string): Promise<CharacterSelectionData> {
    return this.request<CharacterSelectionData>("/player/character", {
      method: "PUT",
      body: JSON.stringify({ character_id: characterId })
    });
  }

  async enterMap(): Promise<MapEnterData> {
    return this.request<MapEnterData>("/map/enter", { method: "POST" });
  }

  async listLevels(): Promise<LevelCatalogData> {
    return this.request<LevelCatalogData>("/level/", { method: "GET" });
  }

  async enterLevel(
    levelId: string,
    entranceId: string,
    idempotencyKey: string
  ): Promise<LevelEnterData> {
    return this.request<LevelEnterData>("/level/enter", {
      method: "POST",
      body: JSON.stringify({ level_id: levelId, entrance_id: entranceId }),
      headers: { "Idempotency-Key": idempotencyKey }
    });
  }

  async startLevel(runId: string): Promise<LevelRunData> {
    return this.request<LevelRunData>("/level/start", {
      method: "POST",
      body: JSON.stringify({ run_id: runId })
    });
  }

  async abandonLevel(runId: string): Promise<LevelRunData> {
    return this.request<LevelRunData>("/level/abandon", {
      method: "POST",
      body: JSON.stringify({ run_id: runId })
    });
  }

  async listRules(): Promise<RuleCatalogData> {
    return this.request<RuleCatalogData>("/level/rules", { method: "GET" });
  }

  async castRule(
    runId: string,
    ruleId: LawRuleId,
    options: { targetId?: string; targetPoint?: RulePoint },
    idempotencyKey: string
  ): Promise<RuleCastData> {
    return this.request<RuleCastData>("/level/rule/cast", {
      method: "POST",
      body: JSON.stringify({
        run_id: runId,
        rule_id: ruleId,
        ...(options.targetId ? { target_id: options.targetId } : {}),
        ...(options.targetPoint ? { target_point: options.targetPoint } : {})
      }),
      headers: { "Idempotency-Key": idempotencyKey }
    });
  }

  async maintainGaze(runId: string, targetId: string): Promise<GazeMaintainData> {
    return this.request<GazeMaintainData>("/level/rule/maintain", {
      method: "POST",
      body: JSON.stringify({ run_id: runId, target_id: targetId })
    });
  }

  async stopGaze(runId: string): Promise<GazeStopData> {
    return this.request<GazeStopData>("/level/rule/stop", {
      method: "POST",
      body: JSON.stringify({ run_id: runId })
    });
  }

  async getLevelState(runId: string): Promise<PersonalLevelState> {
    return this.request<PersonalLevelState>(
      "/level/state/" + encodeURIComponent(runId),
      { method: "GET" }
    );
  }

  async settleLevel(runId: string, idempotencyKey: string): Promise<SettlementData> {
    return this.request<SettlementData>("/level/settle", {
      method: "POST",
      body: JSON.stringify({ run_id: runId }),
      headers: { "Idempotency-Key": idempotencyKey }
    });
  }

  async getPlayerProgress(): Promise<PlayerProgressData> {
    return this.request<PlayerProgressData>("/player/progress", { method: "GET" });
  }

  async listPlayerDiscoveries(): Promise<{ discoveries: DiscoveryItem[] }> {
    return this.request<{ discoveries: DiscoveryItem[] }>("/player/discoveries", { method: "GET" });
  }

  async listPlayerCollections(): Promise<{ collections: CollectionItem[] }> {
    return this.request<{ collections: CollectionItem[] }>("/player/collections", { method: "GET" });
  }

  async listWorldArchive(limit = 50): Promise<{ records: WorldArchiveItem[] }> {
    const safeLimit = Math.min(100, Math.max(1, Math.trunc(limit)));
    return this.request<{ records: WorldArchiveItem[] }>("/world/archive?limit=" + safeLimit, {
      method: "GET"
    });
  }

  async listRewards(): Promise<RewardInboxData> {
    return this.request<RewardInboxData>("/reward", { method: "GET" });
  }

  async claimReward(playerRewardId: string): Promise<RewardClaimData> {
    return this.request<RewardClaimData>("/reward/claim", {
      method: "POST",
      body: JSON.stringify({ player_reward_id: playerRewardId })
    });
  }

  async getLeaderboard(
    boardType: LeaderboardType,
    periodType: LeaderboardPeriod,
    scope: LeaderboardScope = "TOP",
    limit = 20
  ): Promise<LeaderboardData> {
    const safeLimit = Math.min(50, Math.max(1, Math.trunc(limit)));
    const query = [
      "board_type=" + encodeURIComponent(boardType),
      "period_type=" + encodeURIComponent(periodType),
      "scope=" + encodeURIComponent(scope),
      "limit=" + safeLimit
    ].join("&");
    return this.request<LeaderboardData>("/leaderboard?" + query, { method: "GET" });
  }

  private async request<T>(
    path: string,
    options: {
      method: string;
      body?: string;
      authenticated?: boolean;
      requestId?: string;
      headers?: Record<string, string>;
    }
  ): Promise<T> {
    const requestId = options.requestId ?? this.requestId();
    const headers: Record<string, string> = {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Request-Id": requestId
    };
    Object.assign(headers, options.headers);
    const accessToken = this.token();
    if (options.authenticated !== false && accessToken) {
      headers.Authorization = `Bearer ${accessToken}`;
    }

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
        method: options.method,
        headers,
        body: options.body,
        signal: controller.signal
      });
      const payload: unknown = await response.json();
      if (!response.ok) {
        const detail = isRecord(payload) ? payload.detail : undefined;
        const message =
          typeof detail === "string"
            ? detail
            : isRecord(detail) && typeof detail.code === "string"
              ? detail.code
              : `Request failed: ${response.status}`;
        throw new ApiError(message, response.status, undefined, requestId, detail);
      }
      if (!isRecord(payload) || !("data" in payload)) {
        throw new ApiError("Invalid API response envelope", response.status, undefined, requestId);
      }
      return (payload as unknown as ApiEnvelope<T>).data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof Error && error.name === "AbortError") {
        throw new ApiError("Request timed out", 0, undefined, requestId);
      }
      throw new ApiError(
        error instanceof Error ? error.message : "Network request failed",
        0,
        undefined,
        requestId
      );
    } finally {
      clearTimeout(timeout);
    }
  }
}
