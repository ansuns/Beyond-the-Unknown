import type { MapEnterData, MapServerEvent, WsEnvelope } from "./types";

export interface WebSocketLike {
  onopen: ((event: unknown) => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onclose: ((event: { code?: number; reason?: string }) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type WebSocketFactory = (url: string) => WebSocketLike;
export type MapEventHandler = (event: MapServerEvent) => void;

export class MapSocketClient {
  private socket?: WebSocketLike;
  private sequence = 0;
  private ready = false;

  constructor(
    private readonly url: string,
    private readonly factory: WebSocketFactory = (url) => new WebSocket(url) as unknown as WebSocketLike,
    private readonly authTimeoutMs = 8_000
  ) {}

  connect(
    accessToken: string,
    membership: Pick<MapEnterData, "instance_id" | "session_id">,
    onEvent: MapEventHandler,
    reconnect = false,
    onDisconnect?: (event: { code?: number; reason?: string }) => void
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const socket = this.factory(this.url);
      this.socket = socket;
      this.sequence = 0;
      this.ready = false;
      let settled = false;
      const timeout = setTimeout(() => {
        if (!settled) {
          settled = true;
          socket.close(4000, "Handshake timeout");
          reject(new Error("Map WebSocket handshake timed out"));
        }
      }, this.authTimeoutMs);

      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        if (error) reject(error);
        else resolve();
      };

      socket.onopen = () => {
        this.sendRaw("AUTH", { token: accessToken }, 0);
      };
      socket.onmessage = (message) => {
        let event: MapServerEvent;
        try {
          event = JSON.parse(message.data) as MapServerEvent;
        } catch {
          finish(new Error("Invalid WebSocket JSON message"));
          socket.close(4400, "Invalid JSON");
          return;
        }
        if (event?.v !== 1 || typeof event.cmd !== "string" || !event.payload) {
          finish(new Error("Invalid WebSocket message envelope"));
          socket.close(4400, "Invalid envelope");
          return;
        }
        onEvent(event);
        if (event.cmd === "AUTH_FAIL") {
          finish(new Error(String(event.payload.reason ?? "WebSocket authentication failed")));
          socket.close(4401, "Authentication failed");
          return;
        }
        if (event.cmd === "AUTH_OK") {
          this.sendRaw(reconnect ? "RECONNECT" : "ENTER", {
            instance_id: membership.instance_id,
            session_id: membership.session_id
          });
          return;
        }
        if (event.cmd === "ERROR" && !this.ready) {
          finish(new Error(String(event.payload.code ?? "Map entry failed")));
          socket.close(4403, "Map entry failed");
          return;
        }
        if (event.cmd === "ENTER" && !this.ready) {
          this.ready = true;
          finish();
        }
      };
      socket.onerror = () => {
        finish(new Error("Map WebSocket connection failed"));
      };
      socket.onclose = (event) => {
        const wasReady = this.ready;
        this.ready = false;
        if (!settled) {
          finish(new Error(`Map WebSocket closed during handshake (${event.code ?? 0})`));
        } else if (wasReady) {
          onDisconnect?.(event);
        }
      };
    });
  }

  move(x: number, y: number, direction: string, clientTick: number): void {
    this.send("MOVE_SYNC", { x, y, dir: direction, client_tick: clientTick });
  }

  action(actionId: string): void {
    this.send("ACTION_BROADCAST", { action_id: actionId });
  }

  ping(): void {
    this.send("PING", {});
  }

  leave(): void {
    if (this.ready) this.send("LEAVE", {});
    this.socket?.close(1000, "Client leave");
    this.ready = false;
  }

  close(): void {
    this.socket?.close(1000, "Client close");
    this.ready = false;
  }

  private send(command: string, payload: Record<string, unknown>): void {
    if (!this.ready) throw new Error("Map WebSocket is not ready");
    this.sendRaw(command, payload);
  }

  private sendRaw(command: string, payload: Record<string, unknown>, sequence?: number): void {
    const socket = this.socket;
    if (!socket) throw new Error("Map WebSocket is not connected");
    const seq = sequence ?? ++this.sequence;
    this.sequence = Math.max(this.sequence, seq);
    const message: WsEnvelope = {
      v: 1,
      cmd: command,
      seq,
      ts: Date.now(),
      payload
    };
    socket.send(JSON.stringify(message));
  }
}
