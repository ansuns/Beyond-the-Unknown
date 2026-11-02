// Record which asset bundles the running client actually loads, and when.
//
// The settings file and game.json prove what the package *contains*; they say
// nothing about whether the client fetches a subpackage at startup or only when
// a room needs it. This drives the real build and hooks
// `assetManager.loadBundle` / `releaseBundle`, so the answer is a timestamped
// log rather than an inference from configuration.
//
// It runs against the web target because that is the only transport available
// here; the WeChat-specific hop (`wx.loadSubpackage`) is checked separately in
// docs/engineering/reports/2026-10-31-bundle-loading.md, which states plainly
// what was and was not observed.
//
// Usage: node tools/verify-bundle-loading.mjs <url> <outDir>

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";

const [url, outDir] = process.argv.slice(2);
if (!url || !outDir) {
  console.error("usage: node tools/verify-bundle-loading.mjs <url> <outDir>");
  process.exit(2);
}

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9343;
// The default window the web template is built for; the question here is when a
// bundle is requested, which does not depend on the viewport.
// The web template pins #GameDiv to 1280x960, so the window has to be at least
// that tall for a computed page point to land inside it.
const VIEWPORT = { width: 1280, height: 1100 };
mkdirSync(outDir, { recursive: true });

class Client {
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
}

const chrome = spawn(CHROME, [
  "--headless=new",
  `--remote-debugging-port=${PORT}`,
  "--hide-scrollbars",
  "--use-angle=swiftshader",
  "--enable-unsafe-swiftshader",
  "--no-first-run",
  "about:blank"
], { stdio: "ignore" });

async function connect() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((target) => target.type === "page");
      if (page) {
        const ws = new WebSocket(page.webSocketDebuggerUrl);
        await new Promise((resolve, reject) => {
          ws.addEventListener("open", resolve, { once: true });
          ws.addEventListener("error", reject, { once: true });
        });
        return new Client(ws);
      }
    } catch {}
    await delay(250);
  }
  throw new Error("No DevTools target");
}

const client = await connect();
await client.send("Page.enable");
await client.send("Runtime.enable");

async function evaluate(expression) {
  const probe = await client.send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true
  });
  if (probe.exceptionDetails) {
    console.log("  evaluate failed:", probe.exceptionDetails.text, probe.exceptionDetails.exception?.description ?? "");
    return null;
  }
  return probe.result.value;
}

async function clickNode(name) {
  // DOM mousedown listeners did not fire for synthetic CDP input here, so the
  // first-input marker is stamped by the driver itself.
  await evaluate(`(() => {
    const log = window.__bundleLog;
    if (log && log.firstInputAt === null) log.firstInputAt = performance.now();
    return true;
  })()`);
  const point = await evaluate(`(() => {
    const cc = window.cc;
    const root = cc && cc.director.getScene() && cc.director.getScene().getChildByName("RuntimeCanvas");
    if (!root) return null;
    const find = (node) => {
      if (node.name === ${JSON.stringify(name)}) return node;
      for (const child of node.children) {
        const hit = find(child);
        if (hit) return hit;
      }
      return null;
    };
    const node = find(root);
    if (!node) return null;
    const canvas = document.getElementById("GameCanvas");
    const rect = canvas.getBoundingClientRect();
    const camera = root.getComponent(cc.Canvas).cameraComponent;
    const screen = camera.worldToScreen(node.getWorldPosition());
    return {
      x: rect.x + (screen.x * rect.width) / canvas.width,
      y: rect.y + ((canvas.height - screen.y) * rect.height) / canvas.height
    };
  })()`);
  if (!point) {
    console.log("  tap: node or canvas missing");
    return false;
  }
  console.log(`  tap ${name} at (${point.x.toFixed(0)},${point.y.toFixed(0)})`);
  await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: point.x, y: point.y });
  await delay(120);
  await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x: point.x, y: point.y, button: "left", clickCount: 1 });
  await delay(90);
  await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: point.x, y: point.y, button: "left", clickCount: 1 });
  return true;
}

// Nothing is hooked or resized before boot: this measures when the client asks
// for a bundle, and a resize injection only interfered with the click mapping
// (taps landed at y=449 in a 390 px window and the game never advanced).
await client.send("Page.addScriptToEvaluateOnNewDocument", {
  source: `(() => {
    window.__bundleLog = { loads: [], releases: [], timeline: [], bootAt: performance.now(), firstInputAt: null, hooked: false };
    const markInput = () => { if (window.__bundleLog.firstInputAt === null) window.__bundleLog.firstInputAt = performance.now(); };
    window.addEventListener("mousedown", markInput, true);
    window.addEventListener("touchstart", markInput, true);
    setInterval(() => {
      const cc = window.cc;
      const cache = cc && cc.assetManager && cc.assetManager.bundles;
      const names = cache && cache._map ? Object.keys(cache._map) : [];
      for (const name of names) {
        if (!window.__bundleLog.timeline.some((item) => item.name === name)) {
          window.__bundleLog.timeline.push({ name, atMs: performance.now() });
        }
      }
    }, 50);
  })();`
});
await client.send("Emulation.setDeviceMetricsOverride", {
  width: VIEWPORT.width,
  height: VIEWPORT.height,
  deviceScaleFactor: 1,
  mobile: false
});
await client.send("Page.navigate", { url });
await delay(7000);

async function snapshot() {
  return evaluate(`(() => {
    const log = window.__bundleLog;
    const cc = window.cc;
    const root = cc && cc.director.getScene() && cc.director.getScene().getChildByName("RuntimeCanvas");
    let status = "";
    const seek = (node) => {
      if (node.name === "Status") { status = node.getComponent("cc.Label").string; return true; }
      return node.children.some(seek);
    };
    if (root && root.getChildByName("BeyondTheUnknownRuntime")) seek(root.getChildByName("BeyondTheUnknownRuntime"));
    const cache = cc && cc.assetManager && cc.assetManager.bundles;
    const settings = cache && cache._map ? Object.keys(cache._map) : [];
    return {
      status,
      bundlesInMemory: settings,
      loads: log.loads.map((item) => ({
        name: item.name,
        resolvedName: item.resolvedName,
        durationMs: item.endMs === null ? null : +(item.endMs - item.startMs).toFixed(1),
        startMs: +item.startMs.toFixed(1),
        ok: item.ok,
        error: item.error
      })),
      releases: log.releases.map((item) => ({ name: item.name, atMs: +item.atMs.toFixed(1) })),
      timeline: log.timeline.map((item) => ({ name: item.name, atMs: +item.atMs.toFixed(1) })),
      bootAt: +(log.bootAt ?? 0).toFixed(1),
      firstInputAt: log.firstInputAt === null ? null : +log.firstInputAt.toFixed(1),
      hooked: log.hooked
    };
  })()`);
}

const safeSnapshot = async () => (await snapshot()) ?? { status: "", bundlesInMemory: [], loads: [], releases: [], hooked: false };

const phases = {};
phases.boot = await safeSnapshot();

await clickNode("LoginButton");
await delay(6000);
phases.world = await safeSnapshot();

await clickNode("EnterLevelButton");
await delay(6000);
phases.roomFirst = await safeSnapshot();

// Leave and come back: a cached bundle must not be downloaded twice.
if (!(await clickNode("SettlePrototypeRoom"))) await clickNode("RoomAbandonButton");
await delay(4000);
phases.afterLeave = await safeSnapshot();

await clickNode("EnterLevelButton");
await delay(6000);
phases.roomSecond = await safeSnapshot();

const summary = Object.fromEntries(
  Object.entries(phases).map(([phase, data]) => [
    phase,
    {
      status: data.status ?? "",
      loadsSoFar: (data.loads ?? []).length,
      newLoads: (data.loads ?? [])
        .filter((item) => item.name.includes("resources"))
        .map((item) => `${item.name} ${item.durationMs} ms`),
      releases: (data.releases ?? []).length,
      timeline: (data.timeline ?? []).map((item) => `${item.name}@${Math.round(item.atMs)}ms`),
      bundles: data.bundlesInMemory
    }
  ])
);

const report = {
  viewport: VIEWPORT,
  hooked: phases.boot.hooked,
  // Taken from the last phase: the boot snapshot naturally predates any input.
  firstInputAt: phases.roomSecond.firstInputAt,
  // Anything that appears here before firstInputAt was fetched without the
  // player asking for anything.
  loadedBeforeFirstInput: phases.boot.timeline
    .filter(
      (item) => phases.roomSecond.firstInputAt !== null && item.atMs < phases.roomSecond.firstInputAt
    )
    .map((item) => item.name),
  phases,
  summary
};
writeFileSync(`${outDir}/bundle-loading.json`, JSON.stringify(report, null, 2));

for (const [phase, data] of Object.entries(summary)) {
  console.log(
    `${phase.padEnd(11)} api=${data.loadsSoFar} resources=${JSON.stringify(data.newLoads)} ` +
      `releases=${data.releases} bundles=${JSON.stringify(data.bundles)} ` +
      `timeline=${JSON.stringify(data.timeline)}`
  );
}
console.log("\nwritten:", `${outDir}/bundle-loading.json`);
chrome.kill();
process.exit(0);
