// Clicks the canvas and reports which DOM/Cocos input events actually arrive.
// Usage: node tools/probe-input.mjs <url> <x> <y>

import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const [url, xArg, yArg] = process.argv.slice(2);
const x = Number(xArg);
const y = Number(yArg);
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9335;

const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--window-size=1280,900",
  "--use-angle=swiftshader",
  "--enable-unsafe-swiftshader",
  "--no-first-run",
  "about:blank"
], { stdio: "ignore" });

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
const logs = [];
ws.addEventListener("message", (event) => {
  const msg = JSON.parse(event.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg.result);
    pending.delete(msg.id);
  }
  if (msg.method === "Runtime.consoleAPICalled") {
    logs.push(msg.params.args.map((a) => a.value ?? a.description ?? "").join(" "));
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

await send("Runtime.evaluate", {
  expression: `(() => {
    const c = document.getElementById("GameCanvas");
    for (const type of ["pointerdown","mousedown","touchstart","click"]) {
      c.addEventListener(type, (e) => console.log("DOM:" + type + " " + (e.clientX ?? 0) + "," + (e.clientY ?? 0)), true);
    }
    window.addEventListener("resize", () => console.log("resize"));
    return true;
  })()`
});

await send("Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
await delay(150);
await send("Input.dispatchMouseEvent", { type: "mousePressed", x, y, button: "left", buttons: 1, clickCount: 1 });
await delay(120);
await send("Input.dispatchMouseEvent", { type: "mouseReleased", x, y, button: "left", buttons: 0, clickCount: 1 });
await delay(600);

const status = await send("Runtime.evaluate", {
  expression: `(() => {
    const c = document.getElementById("GameCanvas");
    return { w: c.width, h: c.height, rect: c.getBoundingClientRect().toJSON(), dpr: window.devicePixelRatio };
  })()`,
  returnByValue: true
});

console.log("canvas", JSON.stringify(status.result.value));
console.log("logs:", logs.filter((l) => l.includes("DOM:")).join(" | ") || "(no DOM events)");
chrome.kill();
process.exit(0);
