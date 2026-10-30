import { describe, expect, it, vi } from "vitest";
import type { WebSocketLike } from "../assets/scripts/network/map-socket";
import type { MapEnterData } from "../assets/scripts/network/types";
import { MapSession } from "../assets/scripts/world/map-session";
import { SessionStore } from "../assets/scripts/player/session-store";

class FakeSocket implements WebSocketLike {
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onclose: ((event: { code?: number; reason?: string }) => void) | null = null;
  readonly sent: string[] = [];

  send(data: string): void {
    this.sent.push(data);
  }

  open(): void {
    this.onopen?.({});
  }

  message(cmd: string, payload: Record<string, unknown> = {}): void {
    this.onmessage?.({
      data: JSON.stringify({ v: 1, cmd, seq: 0, ts: Date.now(), payload })
    });
  }

  close(code = 1006, reason = "network lost"): void {
    this.onclose?.({ code, reason });
  }
}

const map: MapEnterData = {
  map_id: "MAP_MAIN_001",
  instance_id: "instance-1",
  session_id: "session-1",
  spawn_position: { x: 0, y: 0, direction: "S" },
  current_players: 1,
  max_players: 20,
  reconnect_grace_seconds: 60,
  websocket_path: "/api/v1/ws/map"
};

function handshake(socket: FakeSocket, command: "ENTER" | "RECONNECT"): void {
  socket.open();
  socket.message("AUTH_OK");
  socket.message(command);
}

async function flushMicrotasks(): Promise<void> {
  for (let tick = 0; tick < 10; tick += 1) await Promise.resolve();
}

describe("MapSession reconnect", () => {
  it("reconnects with the same membership during the server grace period", async () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const socketFactory = vi.fn(() => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    });
    const platform = { login: vi.fn().mockResolvedValue("wx-code") };
    const api = {
      login: vi.fn().mockResolvedValue({
        access_token: "access-token",
        token_type: "Bearer",
        expires_in: 3600,
        player_id: "player-1",
        is_new_player: false,
        progress_version: 0,
        server_time: 1
      }),
      enterMap: vi.fn().mockResolvedValue(map)
    };
    const session = new MapSession(
      platform as never,
      api as never,
      new SessionStore(),
      {
        websocketBaseUrl: "wss://example.test",
        socketFactory,
        reconnectInitialDelayMs: 100,
        reconnectMaxDelayMs: 200
      }
    );

    const entering = session.enter(vi.fn());
    await flushMicrotasks();
    expect(sockets).toHaveLength(1);
    handshake(sockets[0], "ENTER");
    await entering;

    sockets[0].close();
    await vi.advanceTimersByTimeAsync(100);
    expect(sockets).toHaveLength(2);
    handshake(sockets[1], "RECONNECT");
    await flushMicrotasks();

    const reconnectCommands = sockets[1].sent.map((raw) => JSON.parse(raw).cmd);
    expect(reconnectCommands).toEqual(["AUTH", "RECONNECT"]);
    expect(platform.login).toHaveBeenCalledOnce();
    expect(api.login).toHaveBeenCalledOnce();
    expect(api.enterMap).toHaveBeenCalledOnce();

    session.leave();
    vi.useRealTimers();
  });

  it("does not reconnect after an intentional leave", async () => {
    vi.useFakeTimers();
    const sockets: FakeSocket[] = [];
    const socketFactory = vi.fn(() => {
      const socket = new FakeSocket();
      sockets.push(socket);
      return socket;
    });
    const platform = { login: vi.fn().mockResolvedValue("wx-code") };
    const api = {
      login: vi.fn().mockResolvedValue({
        access_token: "access-token",
        token_type: "Bearer",
        expires_in: 3600,
        player_id: "player-1",
        is_new_player: false,
        progress_version: 0,
        server_time: 1
      }),
      enterMap: vi.fn().mockResolvedValue(map)
    };
    const session = new MapSession(
      platform as never,
      api as never,
      new SessionStore(),
      { websocketBaseUrl: "wss://example.test", socketFactory }
    );

    const entering = session.enter(vi.fn());
    await flushMicrotasks();
    handshake(sockets[0], "ENTER");
    await entering;

    session.leave();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(sockets).toHaveLength(1);
    vi.useRealTimers();
  });
});
