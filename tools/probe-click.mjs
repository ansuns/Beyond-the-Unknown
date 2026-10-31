// Diagnose what sits under a point on the Cocos canvas.
// Usage: node tools/probe-click.mjs <url> <x> <y>

import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const [url, xArg, yArg] = process.argv.slice(2);
const x = Number(xArg);
const y = Number(yArg);
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9334;

const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    "--window-size=1280,900",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--no-first-run",
    "about:blank"
  ],
  { stdio: "ignore" }
);

async function connect() {
  for (let i = 0; i < 60; i += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await delay(250);
  }
  throw new Error("no devtools");
}

const ws = new WebSocket(await connect());
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
let id = 1;
const pending = new Map();
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg.result);
    pending.delete(msg.id);
  }
});
const send = (method, params = {}) =>
  new Promise((resolve) => {
    const current = id++;
    pending.set(current, resolve);
    ws.send(JSON.stringify({ id: current, method, params }));
  });

await send("Page.enable");
await send("Runtime.enable");
await send("Emulation.setDeviceMetricsOverride", {
  width: 1280,
  height: 900,
  deviceScaleFactor: 1,
  mobile: false
});
await send("Page.navigate", { url });
await delay(6000);

const probe = await send("Runtime.evaluate", {
  expression: `(() => {
    const canvas = document.querySelector("canvas");
    const rect = canvas.getBoundingClientRect();
    const el = document.elementFromPoint(${x}, ${y});
    return {
      canvas: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      hit: el ? el.tagName + " " + (el.id || "") + " " + (el.className || "") : null,
      html: el ? el.outerHTML.slice(0, 160) : null,
      overlays: [...document.querySelectorAll("body > *")].map((n) => {
        const s = getComputedStyle(n);
        return { tag: n.tagName, id: n.id, cls: String(n.className).slice(0,40), pos: s.position, z: s.zIndex, pe: s.pointerEvents };
      })
    };
  })()`,
  returnByValue: true
});
console.log(JSON.stringify(probe.result.value, null, 2));
chrome.kill();
process.exit(0);
