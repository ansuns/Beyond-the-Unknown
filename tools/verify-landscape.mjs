// Verify that the HUD stays inside the visible area at several aspect ratios.
//
// A landscape build can still be wrong: the design resolution is fitted, so a
// control placed at `-visible.height / 2 + 62` moves with the window, while a
// control placed at a fixed pixel offset does not. This drives the real build at
// each ratio and asks the engine for every control's world rectangle, then
// compares it with the visible area - a number, not an eyeball.
//
// Usage: node tools/verify-landscape.mjs <url> <outDir>

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";

const [url, outDir] = process.argv.slice(2);
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9342;
const RATIOS = [
  { name: "16x9", width: 1280, height: 720 },
  { name: "18x9", width: 1440, height: 720 },
  { name: "19.5x9", width: 1560, height: 720 },
  { name: "20x9", width: 1600, height: 720 },
  // The actual DevTools simulator viewport the phone gives us - the four ratios
  // above are 720 px tall and hide what a 390 px tall screen does to the layout.
  { name: "iphone14", width: 844, height: 390 }
];

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

const results = [];
for (const ratio of RATIOS) {
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: ratio.width,
    height: ratio.height,
    deviceScaleFactor: 1,
    mobile: false
  });
  // The web-desktop template pins #GameDiv to a fixed 1280x960 frame, so the
  // window size alone never changes the game viewport. Resize the container
  // before the engine boots, which is exactly what happens on a phone whose
  // canvas fills the screen.
  await client.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `(() => {
      const apply = () => {
        const div = document.getElementById("GameDiv");
        if (div) { div.style.width = "${ratio.width}px"; div.style.height = "${ratio.height}px"; }
        const canvas = document.getElementById("GameCanvas");
        if (canvas) {
          canvas.width = ${ratio.width};
          canvas.height = ${ratio.height};
          canvas.style.width = "${ratio.width}px";
          canvas.style.height = "${ratio.height}px";
        }
      };
      document.addEventListener("DOMContentLoaded", apply);
      window.addEventListener("load", apply);
    })();`
  });
  await client.send("Page.navigate", { url });
  await delay(5000);
  await client.send("Runtime.evaluate", {
    expression: `(() => {
      for (const node of document.querySelectorAll("h1.header, p.footer")) node.remove();
      document.body.style.margin = "0";
      document.documentElement.style.overflow = "hidden";
      return true;
    })()`,
    returnByValue: true
  });
  await delay(500);

  const probe = await client.send("Runtime.evaluate", {
    expression: `(() => {
      const cc = window.cc;
      if (!cc) return { error: "cc missing" };
      const root = cc.director.getScene().getChildByName("RuntimeCanvas");
      const runtime = root && root.getChildByName("BeyondTheUnknownRuntime");
      if (!runtime) return { error: "runtime missing" };
      const view = cc.view;
      const visible = view.getVisibleSize();
      const rect = document.getElementById("GameCanvas").getBoundingClientRect();
      const controls = [];
      const walk = (node) => {
        const transform = node.getComponent("cc.UITransform");
        const label = node.getComponent("cc.Label");
        if (transform && (label || node.name.endsWith("Button"))) {
          const world = node.getWorldPosition();
          const half = { x: transform.width * node.worldScale.x / 2, y: transform.height * node.worldScale.y / 2 };
          controls.push({
            name: node.name,
            text: label ? label.string.slice(0, 12) : "",
            left: world.x - half.x,
            right: world.x + half.x,
            bottom: world.y - half.y,
            top: world.y + half.y
          });
        }
        for (const child of node.children) walk(child);
      };
      walk(runtime);
      return {
        visible: { width: visible.width, height: visible.height },
        canvas: { width: rect.width, height: rect.height },
        controls
      };
    })()`,
    returnByValue: true
  });

  const data = probe.result.value;
  const canvas = await client.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${outDir}/${ratio.name}.png`, Buffer.from(canvas.data, "base64"));

  if (data.error) {
    results.push({ ratio: ratio.name, error: data.error });
    continue;
  }

  // The visible area is centred on the origin: x in [-w/2, w/2], y in [-h/2, h/2].
  const halfW = data.visible.width / 2;
  const halfH = data.visible.height / 2;
  const overflow = data.controls
    .filter((control) => control.top > halfH + 1 || control.bottom < -halfH - 1 ||
      control.right > halfW + 1 || control.left < -halfW - 1)
    .map((control) => `${control.name}(${control.text})`);

  results.push({
    ratio: ratio.name,
    visible: data.visible,
    canvas: data.canvas,
    controls: data.controls.length,
    overflow
  });
}

console.log(JSON.stringify(results, null, 2));
chrome.kill();
process.exit(0);
