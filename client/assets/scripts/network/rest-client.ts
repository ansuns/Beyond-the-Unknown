import type {
  ApiEnvelope,
  LawActionData,
  LawActionKind,
  LawRuleId,
  LevelCatalogData,
  LevelRunData,
  LoginData,
  MapEnterData,
  PersonalMechanismList
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: number,
    readonly requestId?: string
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
  ): Promise<LevelRunData> {
    return this.request<LevelRunData>("/level/enter", {
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

  async applyLawAction(
    runId: string,
    ruleId: LawRuleId,
    mechanismId: string,
    action: LawActionKind,
    idempotencyKey: string
  ): Promise<LawActionData> {
    return this.request<LawActionData>("/level/law/action", {
      method: "POST",
      body: JSON.stringify({
        run_id: runId,
        rule_id: ruleId,
        mechanism_id: mechanismId,
        action
      }),
      headers: { "Idempotency-Key": idempotencyKey }
    });
  }

  async getRunMechanisms(runId: string): Promise<PersonalMechanismList> {
    return this.request<PersonalMechanismList>(
      "/level/runs/" + encodeURIComponent(runId) + "/mechanisms",
      { method: "GET" }
    );
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
      const payload = (await response.json()) as ApiEnvelope<T> | { detail?: string };
      if (!response.ok) {
        const detail = "detail" in payload ? payload.detail : undefined;
        throw new ApiError(detail || `Request failed: ${response.status}`, response.status, undefined, requestId);
      }
      if (!("data" in payload)) {
        throw new ApiError("Invalid API response envelope", response.status, undefined, requestId);
      }
      return payload.data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof Error && error.name === "AbortError") {
        throw new ApiError("Request timed out", 0, undefined, requestId);
      }
      throw new ApiError(error instanceof Error ? error.message : "Network request failed", 0, undefined, requestId);
    } finally {
      clearTimeout(timeout);
    }
  }
}
