import type { WeChatPlatform } from "../platform/wechat-platform";
import type { RestClient } from "../network/rest-client";
import { MapSocketClient, type MapEventHandler, type WebSocketFactory } from "../network/map-socket";
import { SessionStore } from "../player/session-store";
import type { MapEnterData, MapServerEvent } from "../network/types";

export interface MapSessionOptions {
  websocketBaseUrl: string;
  socketFactory?: WebSocketFactory;
  reconnectInitialDelayMs?: number;
  reconnectMaxDelayMs?: number;
}

export class MapSession {
  private socket?: MapSocketClient;
  private map?: MapEnterData;
  private accessToken?: string;
  private eventHandler?: MapEventHandler;
  private reconnectTimer?: ReturnType<typeof setTimeout>;
  private reconnectPromise?: Promise<void>;
  private reconnectStartedAt?: number;
  private reconnectAttempts = 0;
  private socketGeneration = 0;
  private manuallyClosed = false;

  constructor(
    private readonly platform: WeChatPlatform,
    private readonly api: RestClient,
    private readonly session: SessionStore,
    private readonly options: MapSessionOptions
  ) {}

  async enter(onEvent: MapEventHandler, reconnect = false): Promise<MapEnterData> {
    this.manuallyClosed = false;
    this.clearReconnectTimer();
    this.reconnectAttempts = 0;
    this.reconnectStartedAt = undefined;

    const wxCode = await this.platform.login();
    const login = await this.api.login(wxCode);
    this.session.set(login);
    this.accessToken = login.access_token;
    this.map = await this.api.enterMap();
    this.eventHandler = onEvent;

    await this.connectSocket(reconnect);
    return this.map;
  }

  move(x: number, y: number, direction: string, clientTick: number): void {
    this.requireSocket().move(x, y, direction, clientTick);
  }

  action(actionId: string): void {
    this.requireSocket().action(actionId);
  }

  ping(): void {
    this.requireSocket().ping();
  }

  leave(): void {
    this.manuallyClosed = true;
    this.clearReconnectTimer();
    this.socketGeneration += 1;
    this.socket?.leave();
    this.socket = undefined;
    this.map = undefined;
    this.accessToken = undefined;
    this.eventHandler = undefined;
    this.reconnectStartedAt = undefined;
    this.reconnectAttempts = 0;
  }

  dispose(): void {
    this.leave();
    this.session.clear();
  }

  private async connectSocket(reconnect: boolean): Promise<void> {
    if (!this.map || !this.accessToken || !this.eventHandler) {
      throw new Error("Map session has not completed its login and entry bootstrap");
    }
    const wsUrl = new URL(this.map.websocket_path, this.options.websocketBaseUrl).toString();
    const socket = new MapSocketClient(wsUrl, this.options.socketFactory);
    const generation = ++this.socketGeneration;
    this.socket = socket;
    try {
      await socket.connect(
        this.accessToken,
        this.map,
        this.eventHandler,
        reconnect,
        () => this.handleUnexpectedDisconnect(socket, generation)
      );
      if (this.socket === socket) {
        this.reconnectAttempts = 0;
        this.reconnectStartedAt = undefined;
      }
    } catch (error) {
      if (this.socket === socket) this.socket = undefined;
      throw error;
    }
  }

  private handleUnexpectedDisconnect(
    socket: MapSocketClient,
    generation: number
  ): void {
    if (
      this.manuallyClosed ||
      generation !== this.socketGeneration ||
      this.socket !== socket
    ) return;
    this.socket = undefined;
    if (this.reconnectStartedAt === undefined) {
      this.reconnectStartedAt = Date.now();
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    if (this.manuallyClosed || this.reconnectTimer !== undefined || !this.map) return;
    const graceMs = Math.max(0, this.map.reconnect_grace_seconds * 1000);
    const startedAt = this.reconnectStartedAt ?? Date.now();
    const remainingMs = graceMs - (Date.now() - startedAt);
    if (remainingMs <= 0) {
      this.failReconnectGrace();
      return;
    }

    const initialDelay = Math.max(100, this.options.reconnectInitialDelayMs ?? 500);
    const maxDelay = Math.max(initialDelay, this.options.reconnectMaxDelayMs ?? 4_000);
    const delay = Math.min(initialDelay * 2 ** this.reconnectAttempts, maxDelay, remainingMs);
    this.reconnectAttempts += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined;
      void this.reconnect();
    }, delay);
  }

  private async reconnect(): Promise<void> {
    if (this.manuallyClosed || !this.map || this.reconnectPromise) return;
    const graceMs = Math.max(0, this.map.reconnect_grace_seconds * 1000);
    const startedAt = this.reconnectStartedAt ?? Date.now();
    if (Date.now() - startedAt >= graceMs) {
      this.failReconnectGrace();
      return;
    }

    this.reconnectPromise = this.connectSocket(true)
      .catch(() => {
        this.scheduleReconnect();
      })
      .finally(() => {
        this.reconnectPromise = undefined;
      });
    await this.reconnectPromise;
  }

  private failReconnectGrace(): void {
    this.manuallyClosed = true;
    this.clearReconnectTimer();
    this.socket = undefined;
    const event: MapServerEvent = {
      v: 1,
      cmd: "ERROR",
      seq: 0,
      ts: Date.now(),
      payload: { code: "RECONNECT_EXPIRED" }
    };
    this.eventHandler?.(event);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== undefined) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = undefined;
    }
  }

  private requireSocket(): MapSocketClient {
    if (!this.socket) throw new Error("Player has not entered the shared map");
    return this.socket;
  }
}
