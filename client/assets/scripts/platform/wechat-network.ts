import type { FetchLike, HttpResponseLike } from "../network/rest-client";
import type { WebSocketFactory, WebSocketLike } from "../network/map-socket";

interface WxRequestResponse {
  statusCode: number;
  data: unknown;
}

interface WxRequestTask {
  abort?: () => void;
}

interface WxSocketTask {
  onOpen(callback: (event: unknown) => void): void;
  onMessage(callback: (event: { data: string | ArrayBuffer }) => void): void;
  onError(callback: (event: unknown) => void): void;
  onClose(callback: (event: { code?: number; reason?: string }) => void): void;
  send(options: { data: string }): void;
  close(options?: { code?: number; reason?: string }): void;
}

export interface WeChatNetworkApi {
  request(options: {
    url: string;
    method: string;
    header: Record<string, string>;
    data?: unknown;
    success: (response: WxRequestResponse) => void;
    fail: (error: unknown) => void;
  }): WxRequestTask;
  connectSocket(options: { url: string }): WxSocketTask;
}

class WeChatResponse implements HttpResponseLike {
  readonly ok: boolean;

  constructor(readonly status: number, private readonly data: unknown) {
    this.ok = status >= 200 && status < 300;
  }

  async json(): Promise<unknown> {
    if (typeof this.data === "string") return JSON.parse(this.data) as unknown;
    return this.data;
  }
}

export function createWeChatFetch(wx: WeChatNetworkApi): FetchLike {
  return (input, init = {}) => new Promise((resolve, reject) => {
    if (init.signal?.aborted) {
      const error = new Error("Request aborted");
      error.name = "AbortError";
      reject(error);
      return;
    }
    let data: unknown;
    if (typeof init.body === "string") {
      try { data = JSON.parse(init.body) as unknown; }
      catch { data = init.body; }
    } else {
      data = init.body;
    }
    let task: WxRequestTask | undefined;
    const abort = () => {
      task?.abort?.();
      const error = new Error("Request aborted");
      error.name = "AbortError";
      reject(error);
    };
    init.signal?.addEventListener("abort", abort, { once: true });
    task = wx.request({
      url: String(input),
      method: init.method ?? "GET",
      header: (init.headers ?? {}) as Record<string, string>,
      data,
      success: (response) => {
        init.signal?.removeEventListener("abort", abort);
        resolve(new WeChatResponse(response.statusCode, response.data));
      },
      fail: (error) => {
        init.signal?.removeEventListener("abort", abort);
        reject(error instanceof Error ? error : new Error("WeChat request failed"));
      }
    });
  });
}

class WeChatSocketAdapter implements WebSocketLike {
  onopen: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onclose: ((event: { code?: number; reason?: string }) => void) | null = null;

  constructor(private readonly task: WxSocketTask) {
    task.onOpen((event) => this.onopen?.(event));
    task.onMessage((event) => {
      const data = typeof event.data === "string"
        ? event.data
        : new TextDecoder().decode(event.data);
      this.onmessage?.({ data });
    });
    task.onError((event) => this.onerror?.(event));
    task.onClose((event) => this.onclose?.(event));
  }

  send(data: string): void {
    this.task.send({ data });
  }

  close(code = 1000, reason = ""): void {
    this.task.close({ code, reason });
  }
}

export function createWeChatWebSocketFactory(wx: WeChatNetworkApi): WebSocketFactory {
  return (url) => new WeChatSocketAdapter(wx.connectSocket({ url }));
}
