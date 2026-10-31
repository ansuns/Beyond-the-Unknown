// Minimal Chrome DevTools Protocol client.
//
// Node 22 ships a global WebSocket, so driving a real browser needs no
// dependency: start Chrome with --remote-debugging-port, open the page target's
// debugger URL and speak JSON-RPC over it.
//
// Kept here so the screenshot, layout and bundle probes stop each carrying
// their own copy of the same 60 lines.

import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

export const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";

export async function launchChrome(port, { width = 1280, height = 1000 } = {}) {
  const chrome = spawn(
    CHROME,
    [
      "--headless=new",
      `--remote-debugging-port=${port}`,
      `--window-size=${width},${height}`,
      "--hide-scrollbars",
      "--use-angle=swiftshader",
      "--enable-unsafe-swiftshader",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-extensions",
      // The build is served from 127.0.0.1. Chrome otherwise inherits the
      // machine's proxy settings and sends loopback requests through it, so
      // the page loads nothing and every probe reports "no canvas".
      "--no-proxy-server",
      "--proxy-bypass-list=*",
      "about:blank"
    ],
    { stdio: "ignore" }
  );

  for (let attempt = 0; attempt < 80; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) return chrome;
    } catch {
      // DevTools is not listening yet.
    }
    await delay(250);
  }
  throw new Error("Chrome DevTools endpoint never came up");
}

export class CdpClient {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression, { awaitPromise = true } = {}) {
    const result = await this.send("Runtime.evaluate", {
      expression: `(() => { ${expression} })()`,
      returnByValue: true,
      awaitPromise
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description ?? "evaluation failed");
    }
    return result.result.value;
  }
}

export async function connectPage(port) {
  const list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const page = list.find((target) => target.type === "page");
  if (!page) throw new Error("No page target available");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  return new CdpClient(ws);
}
