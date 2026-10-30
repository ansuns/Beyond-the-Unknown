import type { WeChatPlatform } from "../platform/wechat-platform";
import type { RestClient } from "../network/rest-client";
import { MapSocketClient, type MapEventHandler, type WebSocketFactory } from "../network/map-socket";
import { SessionStore } from "../player/session-store";
import type { MapEnterData } from "../network/types";

export interface MapSessionOptions {
  websocketBaseUrl: string;
  socketFactory?: WebSocketFactory;
}

export class MapSession {
  private socket?: MapSocketClient;

  constructor(
    private readonly platform: WeChatPlatform,
    private readonly api: RestClient,
    private readonly session: SessionStore,
    private readonly options: MapSessionOptions
  ) {}

  async enter(onEvent: MapEventHandler, reconnect = false): Promise<MapEnterData> {
    const wxCode = await this.platform.login();
    const login = await this.api.login(wxCode);
    this.session.set(login);
    const map = await this.api.enterMap();
    const wsUrl = new URL(map.websocket_path, this.options.websocketBaseUrl).toString();
    const socket = new MapSocketClient(wsUrl, this.options.socketFactory);
    await socket.connect(login.access_token, map, onEvent, reconnect);
    this.socket = socket;
    return map;
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
    this.socket?.leave();
    this.socket = undefined;
  }

  dispose(): void {
    this.socket?.close();
    this.socket = undefined;
    this.session.clear();
  }

  private requireSocket(): MapSocketClient {
    if (!this.socket) throw new Error("Player has not entered the shared map");
    return this.socket;
  }
}
