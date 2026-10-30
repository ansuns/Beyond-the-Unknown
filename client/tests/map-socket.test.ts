import { describe, expect, it, vi } from "vitest";
import { MapSocketClient, type WebSocketLike } from "../assets/scripts/network/map-socket";

class FakeSocket implements WebSocketLike {
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onclose: ((event: { code?: number; reason?: string }) => void) | null = null;
  sent: Array<Record<string, unknown>> = [];
  send(data: string): void { this.sent.push(JSON.parse(data) as Record<string, unknown>); }
  close(code = 1000, reason = ""): void { this.onclose?.({ code, reason }); }
  receive(cmd: string, payload: Record<string, unknown> = {}): void {
    this.onmessage?.({ data: JSON.stringify({ v: 1, cmd, seq: 1, ts: 1, payload }) });
  }
}

describe("MapSocketClient", () => {
  it("sends AUTH first, then ENTER with increasing sequence numbers", async () => {
    const socket = new FakeSocket();
    const events: string[] = [];
    const client = new MapSocketClient("wss://example.test/api/v1/ws/map", () => socket);
    const connecting = client.connect("jwt", {
      instance_id: "instance-1", session_id: "session-1"
    }, (event) => events.push(event.cmd));

    socket.onopen?.({});
    expect(socket.sent[0]).toMatchObject({ cmd: "AUTH", seq: 0, payload: { token: "jwt" } });
    socket.receive("AUTH_OK");
    expect(socket.sent[1]).toMatchObject({
      cmd: "ENTER", seq: 1,
      payload: { instance_id: "instance-1", session_id: "session-1" }
    });
    socket.receive("ENTER", { players: [] });
    await connecting;
    expect(events).toEqual(["AUTH_OK", "ENTER"]);

    client.move(1, 2, "E", 100);
    expect(socket.sent[2]).toMatchObject({ cmd: "MOVE_SYNC", seq: 2 });
  });

  it("rejects authentication failures", async () => {
    const socket = new FakeSocket();
    const client = new MapSocketClient("wss://example.test/ws", () => socket);
    const connecting = client.connect("bad-token", {
      instance_id: "instance", session_id: "session"
    }, () => undefined);
    socket.onopen?.({});
    socket.receive("AUTH_FAIL", { reason: "Invalid access token" });
    await expect(connecting).rejects.toThrow("Invalid access token");
  });
});
