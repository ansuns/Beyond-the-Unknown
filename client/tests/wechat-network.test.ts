import { describe, expect, it, vi } from "vitest";
import {
  createWeChatFetch,
  createWeChatWebSocketFactory,
  type WeChatNetworkApi
} from "../assets/scripts/platform/wechat-network";

describe("WeChat native networking adapters", () => {
  it("maps REST requests to wx.request and returns a fetch-like response", async () => {
    const wx: WeChatNetworkApi = {
      request: vi.fn((options) => {
        options.success({ statusCode: 200, data: { ok: true } });
        return {};
      }),
      connectSocket: vi.fn()
    };
    const fetchLike = createWeChatFetch(wx);
    const response = await fetchLike("https://api.example.test/api/v1/player/me", {
      method: "GET",
      headers: { Authorization: "Bearer token" }
    });
    expect(response.ok).toBe(true);
    expect(await response.json()).toEqual({ ok: true });
    expect(wx.request).toHaveBeenCalledWith(expect.objectContaining({
      url: "https://api.example.test/api/v1/player/me",
      method: "GET",
      header: { Authorization: "Bearer token" }
    }));
  });

  it("bridges WeChat SocketTask events and sends", () => {
    let onOpen: ((event: unknown) => void) | undefined;
    let onMessage: ((event: { data: string | ArrayBuffer }) => void) | undefined;
    const send = vi.fn();
    const close = vi.fn();
    const wx: WeChatNetworkApi = {
      request: vi.fn(),
      connectSocket: vi.fn(() => ({
        onOpen: (callback) => { onOpen = callback; },
        onMessage: (callback) => { onMessage = callback; },
        onError: vi.fn(),
        onClose: vi.fn(),
        send,
        close
      }))
    };
    const socket = createWeChatWebSocketFactory(wx)("wss://api.example.test/api/v1/ws/map");
    const opened = vi.fn();
    const messaged = vi.fn();
    socket.onopen = opened;
    socket.onmessage = messaged;
    onOpen?.({});
    onMessage?.({ data: "hello" });
    socket.send("ping");
    socket.close(1000, "done");
    expect(opened).toHaveBeenCalledOnce();
    expect(messaged).toHaveBeenCalledWith({ data: "hello" });
    expect(send).toHaveBeenCalledWith({ data: "ping" });
    expect(close).toHaveBeenCalledWith({ code: 1000, reason: "done" });
  });
});
