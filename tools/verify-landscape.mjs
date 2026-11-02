// Measure the landscape layout instead of eyeballing it.
//
// The first version of this tool asked one question: is every control inside the
// visible area? That check passed an 844x390 screen where the stats overlay sat
// on the login button, the rules label sat on the map and the room's action
// buttons sat in the middle of the room on top of the player - nothing was out
// of bounds, everything was unusable.
//
// So this version drives three real states (menu, world map, room) and answers
// six separate questions, because collapsing them into one PASS is what hid
// those bugs:
//
//   1. overflow        - a control leaves the visible area
//   2. overlaps        - two controls collide (both can be fully on screen)
//   3. touch conflicts - two touch rectangles intersect, so one never gets taps
//   4. covered targets - an interactive object sits under the HUD
//   5. minimum size    - how many canvas pixels the player actually is
//   6. safe area       - interactive controls too close to a screen edge
//
// Usage: node tools/verify-landscape.mjs <url> <outDir>

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";

import {
  detectCoveredTargets,
  detectOverflows,
  detectOverlaps,
  detectSafeAreaViolations,
  detectTouchConflicts,
  minVisualSize
} from "./lib/layout-geometry.mjs";

const [url, outDir] = process.argv.slice(2);
if (!url || !outDir) {
  console.error("usage: node tools/verify-landscape.mjs <url> <outDir>");
  process.exit(2);
}

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9342;
const RATIOS = [
  { name: "16x9", width: 1280, height: 720 },
  { name: "18x9", width: 1440, height: 720 },
  { name: "19.5x9", width: 1560, height: 720 },
  { name: "20x9", width: 1600, height: 720 },
  // The real DevTools simulator viewport. The four ratios above are all 720 px
  // tall and hide what a 390 px tall screen does to the layout.
  { name: "844x390", width: 844, height: 390 }
];

// Things drawn inside the room that a player is meant to reach. If the HUD
// covers one of these, the room cannot be played.
const TARGET_NAMES = ["Player", "HiddenObject", "LightMarker", "ExitGate", "HiddenCore"];

// Touch overlaps that exist on purpose: the joystick must take drags over the
// map, otherwise moving would also walk the player by tapping through it.
const ACCEPTED_TOUCH_CONFLICTS = [["WorldViewport", "VirtualJoystick"]];

// The room left a level run open, so the next ratio's enter was refused with
// "Player already has an active level run". Settling between ratios keeps every
// measured room real instead of only the first.
const SETTLE_BUTTON = "SettlePrototypeRoom";

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
  const probe = await client.send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  return probe.result.value;
}

async function clickNode(name) {
  const point = await evaluate(`(() => {
    const cc = window.cc;
    const root = cc.director.getScene().getChildByName("RuntimeCanvas");
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
    console.log(`  tap ${name}: node not found`);
    return false;
  }
  await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: point.x, y: point.y });
  await delay(120);
  await client.send("Input.dispatchMouseEvent", { type: "mousePressed", x: point.x, y: point.y, button: "left", clickCount: 1 });
  await delay(90);
  await client.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: point.x, y: point.y, button: "left", clickCount: 1 });
  return true;
}

async function screenshot(file) {
  const shot = await client.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${outDir}/${file}.png`, Buffer.from(shot.data, "base64"));
}

// One probe that reports every UI node with its real rectangle.
// getBoundingBoxToWorld accounts for anchors, scale and rotation, which is what
// the touch dispatcher hit-tests against, and hasEventListener tells us which
// nodes can actually swallow a tap.
const PROBE = `(() => {
  const cc = window.cc;
  if (!cc) return { error: "cc missing" };
  const canvas = cc.director.getScene().getChildByName("RuntimeCanvas");
  const runtime = canvas && canvas.getChildByName("BeyondTheUnknownRuntime");
  if (!runtime) return { error: "runtime missing" };
  const view = cc.view;
  const visible = view.getVisibleSize();
  const element = document.getElementById("GameCanvas");
  const rect = element.getBoundingClientRect();
  const touchTypes = ["touch-start", "touch-move", "touch-end", "touch-cancel"];
  const nodes = [];
  const walk = (node, parentPath) => {
    const transform = node.getComponent("cc.UITransform");
    const path = parentPath ? parentPath + "/" + node.name : node.name;
    if (transform) {
      const box = transform.getBoundingBoxToWorld();
      const label = node.getComponent("cc.Label");
      const sprite = node.getComponent("cc.Sprite");
      let kind = "graphics";
      if (label) kind = "label";
      else if (node.name.endsWith("Button")) kind = "button";
      else if (sprite) kind = "sprite";
      else if (node.children.length) kind = "container";
      nodes.push({
        name: node.name,
        path,
        kind,
        touchTarget: touchTypes.some((type) => node.hasEventListener(type)),
        left: box.xMin,
        right: box.xMax,
        bottom: box.yMin,
        top: box.yMax
      });
    }
    for (const child of node.children) walk(child, path);
  };
  walk(runtime, "");
  let status = "";
  const seek = (node) => {
    if (node.name === "Status") {
      const label = node.getComponent("cc.Label");
      status = label ? label.string : "";
      return true;
    }
    return node.children.some(seek);
  };
  seek(runtime);
  return {
    visible: { width: visible.width, height: visible.height },
    canvas: { width: rect.width, height: rect.height, pixels: { width: element.width, height: element.height } },
    status,
    nodes
  };
})()`;

function analyse(probe, options = {}) {
  const { visible, canvas, nodes, status } = probe;
  // Design units map onto the canvas at this scale, so sizes are reported in the
  // pixels a phone actually draws rather than in arbitrary units.
  const pixelWidth = Number(canvas.pixels?.width ?? canvas.width);
  const pixelsPerUnit = Number.isFinite(pixelWidth) && visible.width ? pixelWidth / visible.width : 0;
  const targets = nodes.filter((node) =>
    TARGET_NAMES.some((name) => node.name === name || node.name.startsWith(`${name}-`))
  );
  const occluders = nodes.filter(
    (node) =>
      node.touchTarget &&
      !TARGET_NAMES.some((name) => node.name === name || node.name.startsWith(`${name}-`))
  );

  return {
    status,
    visible,
    canvas,
    pixelsPerUnit: +pixelsPerUnit.toFixed(4),
    nodes: nodes.length,
    interactive: nodes.filter((node) => node.touchTarget).length,
    targets: targets.map((node) => node.name),
    overflow: detectOverflows(nodes, visible),
    overlaps: detectOverlaps(nodes),
    blockingOverlaps: detectOverlaps(nodes).filter((item) => item.severity === "blocking").length,
    touchConflicts: detectTouchConflicts(nodes, { accepted: ACCEPTED_TOUCH_CONFLICTS }),
    touchConflictDefects: detectTouchConflicts(nodes, { accepted: ACCEPTED_TOUCH_CONFLICTS }).filter(
      (item) => !item.intentional
    ).length,
    coveredTargets: targets.length ? detectCoveredTargets(targets, occluders, { threshold: 0.2 }) : [],
    safeArea: detectSafeAreaViolations(nodes, visible, 8),
    smallestTarget: options.expectPlayer && targets.length
      ? (() => {
          const worst = minVisualSize(targets, pixelsPerUnit);
          // minVisualSize already returns the rendered size; asking for it a
          // second time would measure the summary object, not the node, and
          // produce NaN.
          return {
            name: worst.name,
            width_px: +worst.width_px.toFixed(1),
            height_px: +worst.height_px.toFixed(1),
            smaller_px: worst.smaller_px
          };
        })()
      : null
  };
}

const report = [];
for (const ratio of RATIOS) {
  console.log(`== ${ratio.name} (${ratio.width}x${ratio.height}) ==`);
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: ratio.width,
    height: ratio.height,
    deviceScaleFactor: 1,
    mobile: false
  });
  // The web-desktop template pins #GameDiv to a fixed 1280x960 frame, so the
  // window size alone never changes the game viewport. Resize the container
  // before the engine boots, which is what a phone whose canvas fills the
  // screen does.
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
  await delay(6500);
  await evaluate(`(() => {
    for (const node of document.querySelectorAll("h1.header, p.footer")) node.remove();
    document.body.style.margin = "0";
    document.documentElement.style.overflow = "hidden";
    return true;
  })()`);
  await delay(400);

  const entry = { ratio: ratio.name, window: { width: ratio.width, height: ratio.height }, phases: {} };

  const menu = await evaluate(PROBE);
  if (menu.error) {
    entry.error = menu.error;
    report.push(entry);
    console.log("  ERROR", menu.error);
    continue;
  }
  entry.phases.menu = analyse(menu);
  await screenshot(`${ratio.name}-menu`);

  const loggedIn = await clickNode("LoginButton");
  await delay(6500);
  entry.phases.world = analyse(await evaluate(PROBE));
  entry.phases.world.loginTapped = loggedIn;
  await screenshot(`${ratio.name}-world`);

  entry.phases.room = { enterTapped: await clickNode("EnterLevelButton") };
  await delay(6000);
  entry.phases.room = analyse(await evaluate(PROBE), { expectPlayer: true });
  await screenshot(`${ratio.name}-room`);

  // Close the level run before moving to the next ratio: ROOM-01 exposes only
  // "放弃返回" (abandon), which also releases the run server-side.
  if (!(await clickNode(SETTLE_BUTTON))) await clickNode("RoomAbandonButton");
  await delay(4000);
  const settled = await evaluate(PROBE);
  entry.phases.room.settledStatus = settled.status;

  for (const [phase, data] of Object.entries(entry.phases)) {
    if (data.nodes === undefined) continue;
    console.log(
      `  ${phase.padEnd(6)} nodes=${String(data.nodes).padStart(3)} touch=${String(data.interactive).padStart(2)} ` +
        `overflow=${data.overflow.length} overlaps=${data.overlaps.length} ` +
        `touchConflicts=${data.touchConflictDefects} coveredTargets=${data.coveredTargets.length} ` +
        `safeArea=${data.safeArea.length}`
    );
    if (data.smallestTarget) {
      console.log(
        `         smallest target ${data.smallestTarget.name}: ` +
          `${data.smallestTarget.width_px}x${data.smallestTarget.height_px} px`
      );
    }
  }
  report.push(entry);
}

writeFileSync(`${outDir}/landscape-geometry.json`, JSON.stringify(report, null, 2));

console.log("\n== summary ==");
console.log(
  "ratio     overflow overlaps blocking touchDefects coveredTargets safeArea smallestTargetPx"
);
for (const entry of report) {
  const phases = Object.values(entry.phases).filter((phase) => phase.nodes !== undefined);
  const sum = (key) => phases.reduce((total, phase) => total + phase[key].length, 0);
  const count = (key) => phases.reduce((total, phase) => total + (phase[key] ?? 0), 0);
  console.log(
    `${entry.ratio.padEnd(9)} ${String(sum("overflow")).padStart(8)} ${String(sum("overlaps")).padStart(8)} ` +
      `${String(count("blockingOverlaps")).padStart(8)} ${String(count("touchConflictDefects")).padStart(12)} ` +
      `${String(sum("coveredTargets")).padStart(14)} ${String(sum("safeArea")).padStart(8)} ` +
      `${String(entry.phases.room?.smallestTarget?.smaller_px ?? "-").padStart(16)}`
  );
}

console.log("\nwritten:", `${outDir}/landscape-geometry.json`);
chrome.kill();
process.exit(0);
