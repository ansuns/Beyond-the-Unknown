// @ts-nocheck
// Lets the Cocos web build run outside WeChat.
//
// The runtime calls wx.login / wx.request / wx.connectSocket directly, which is
// correct for the mini game but leaves the browser preview blank - the normal
// iteration loop for a Cocos project. These adapters provide the same shapes
// over fetch and WebSocket, and a stable per-browser login code so a reload
// keeps the same player instead of creating a new one every time.
//
// This is a development and preview path only: the server refuses the matching
// local login unless LOCAL_LOGIN_ENABLED is set, and never in production.

import type { FetchLike, HttpResponseLike } from "../network/rest-client";
import type { WebSocketFactory, WebSocketLike } from "../network/map-socket";

const DEVICE_KEY = "btu.device_code";

export function hasWeChatApi(): boolean {
  const api = (globalThis as any).wx;
  return Boolean(api && typeof api.login === "function");
}

/** Stable pseudo device id for browser sessions. */
export function browserLoginCode(): string {
  try {
    const stored = globalThis.localStorage?.getItem(DEVICE_KEY);
    if (stored) return stored;
    const created = `browser-${Math.random().toString(36).slice(2, 10)}`;
    globalThis.localStorage?.setItem(DEVICE_KEY, created);
    return created;
  } catch {
    // Private mode can throw on localStorage; a per-load code still works, it
    // just creates a fresh player each reload.
    return `browser-${Math.random().toString(36).slice(2, 10)}`;
  }
}

export class BrowserPlatform {
  async login(): Promise<string> {
    return browserLoginCode();
  }
}

class BrowserResponse implements HttpResponseLike {
  readonly ok: boolean;

  constructor(readonly status: number, private readonly payload: unknown) {
    this.ok = status >= 200 && status < 300;
  }

  async json(): Promise<unknown> {
    return this.payload;
  }
}

export function createBrowserFetch(): FetchLike {
  return async (input, init) => {
    const response = await globalThis.fetch(input as any, init);
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      payload = null;
    }
    return new BrowserResponse(response.status, payload);
  };
}

export function createBrowserWebSocketFactory(): WebSocketFactory {
  return (url: string) => {
    const socket = new WebSocket(url);
    return {
      get onopen() {
        return socket.onopen as any;
      },
      set onopen(handler: any) {
        socket.onopen = handler;
      },
      get onmessage() {
        return socket.onmessage as any;
      },
      set onmessage(handler: any) {
        socket.onmessage = handler;
      },
      get onerror() {
        return socket.onerror as any;
      },
      set onerror(handler: any) {
        socket.onerror = handler;
      },
      get onclose() {
        return socket.onclose as any;
      },
      set onclose(handler: any) {
        socket.onclose = handler;
      },
      send(data: string) {
        socket.send(data);
      },
      close(code?: number, reason?: string) {
        socket.close(code, reason);
      }
    } as WebSocketLike;
  };
}
