// Drives headless Chrome over the DevTools protocol to screenshot the Cocos
// web build at real interaction points. Node 22 ships a global WebSocket, so
// this needs no package install.
//
// Usage: node tools/drive-screenshot.mjs <url> <outDir> [width] [height]

import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";

const [url, outDir, widthArg, heightArg] = process.argv.slice(2);
const width = Number(widthArg ?? 1280);
const height = Number(heightArg ?? 1000);

const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;

mkdirSync(outDir, { recursive: true });

const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    `--remote-debugging-port=${PORT}`,
    `--window-size=${width},${height}`,
    "--hide-scrollbars",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-extensions",
    "about:blank"
  ],
  { stdio: "ignore" }
);

async function waitForDevTools() {
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      if (response.ok) return;
    } catch {
      // Not listening yet.
    }
    await delay(250);
  }
  throw new Error("Chrome DevTools endpoint never came up");
}

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

async function connect() {
  const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
  const page = list.find((target) => target.type === "page");
  if (!page) throw new Error("No page target available");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  return new Client(ws);
}

async function main() {
  await waitForDevTools();
  const client = await connect();
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  await client.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false
  });

  const consoleLines = [];
  client.ws.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.method === "Runtime.consoleAPICalled") {
      const text = (message.params.args ?? [])
        .map((arg) => arg.value ?? arg.description ?? "")
        .join(" ");
      consoleLines.push(`[${message.params.type}] ${text}`);
    }
    if (message.method === "Runtime.exceptionThrown") {
      consoleLines.push(`[exception] ${message.params.exceptionDetails.text}`);
    }
  });

  // The web-desktop template pins #GameDiv to a fixed 1280x960 frame, so the
  // window size alone never changes the game viewport - at 844x390 the capture
  // was a zoomed crop of a 1280-wide canvas. Resize the container before the
  // engine boots, which is what a phone whose canvas fills the screen does.
  await client.send("Page.addScriptToEvaluateOnNewDocument", {
    source: `(() => {
      const apply = () => {
        const div = document.getElementById("GameDiv");
        if (div) { div.style.width = "${width}px"; div.style.height = "${height}px"; }
        const canvas = document.getElementById("GameCanvas");
        if (canvas) {
          canvas.width = ${width};
          canvas.height = ${height};
          canvas.style.width = "${width}px";
          canvas.style.height = "${height}px";
        }
      };
      document.addEventListener("DOMContentLoaded", apply);
      window.addEventListener("load", apply);
    })();`
  });
  await client.send("Page.navigate", { url });
  await delay(6000);

  // The web template puts a title and a footer around the canvas. Both make the
  // page scroll, which moves the canvas between measuring a tap target and
  // tapping it, and both eat vertical space the game needs. Strip them so the
  // canvas sits still at a known origin.
  await client.send("Runtime.evaluate", {
    expression: `(() => {
      for (const node of document.querySelectorAll("h1.header, p.footer")) node.remove();
      document.body.style.margin = "0";
      document.documentElement.style.overflow = "hidden";
      document.body.style.overflow = "hidden";
      return true;
    })()`,
    returnByValue: true
  });
  await delay(600);

  async function shot(name) {
    const { data } = await client.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(`${outDir}/${name}.png`, Buffer.from(data, "base64"));
  }

  /**
   * Convert a Cocos node position (origin at the centre of the visible area) to
   * page coordinates using the engine's own view matrix. Deriving this from the
   * design resolution by hand gets the scale and the y-flip wrong, and a tap
   * that lands 20px off looks exactly like a broken button.
   */
  async function designToPage(x, y) {
    const probe = await client.send("Runtime.evaluate", {
      expression: `(() => {
        const cc = window.cc;
        const canvas = document.getElementById("GameCanvas") || document.querySelector("canvas");
        if (!cc || !canvas) return null;
        const view = cc.view;
        const rect = canvas.getBoundingClientRect();
        const visible = view.getVisibleSize();
        const viewport = view.getViewportRect();
        const px = viewport.x + (${x} + visible.width / 2) * view.getScaleX();
        const py = viewport.y + viewport.height - (${y} + visible.height / 2) * view.getScaleY();
        return {
          x: rect.x + (px * rect.width) / canvas.width,
          y: rect.y + (py * rect.height) / canvas.height,
          scale: view.getScaleX(),
          visible: { width: visible.width, height: visible.height }
        };
      })()`,
      returnByValue: true
    });
    if (!probe.result.value) throw new Error("Cocos view is not reachable from the page");
    return probe.result.value;
  }

  /**
   * Click a UI node by name.
   *
   * Converting design coordinates by hand is unreliable here: the layout is
   * built from view.getVisibleSize(), which changes with the window, and the
   * camera applies its own scale. Asking the engine for the node's world
   * position and screen point removes both guesses.
   */
  async function clickNode(name) {
    const probe = await client.send("Runtime.evaluate", {
      expression: `(() => {
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
          y: rect.y + ((canvas.height - screen.y) * rect.height) / canvas.height,
          found: true
        };
      })()`,
      returnByValue: true
    });
    const point = probe.result.value;
    if (!point) {
      console.log(`tap ${name}: node not found`);
      return false;
    }
    console.log(`tap ${name} -> page(${point.x.toFixed(1)},${point.y.toFixed(1)})`);
    await client.send("Input.dispatchMouseEvent", { type: "mouseMoved", x: point.x, y: point.y });
    await delay(120);
    await client.send("Input.dispatchMouseEvent", {
      type: "mousePressed",
      x: point.x,
      y: point.y,
      button: "left",
      buttons: 1,
      clickCount: 1
    });
    await delay(90);
    await client.send("Input.dispatchMouseEvent", {
      type: "mouseReleased",
      x: point.x,
      y: point.y,
      button: "left",
      buttons: 0,
      clickCount: 1
    });
    return true;
  }

  async function clickDesign(x, y) {
    const point = await designToPage(x, y);
    console.log(
      `tap design(${x},${y}) -> page(${point.x.toFixed(1)},${point.y.toFixed(1)}) scale=${point.scale.toFixed(3)}`
    );
    await client.send("Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x: point.x,
      y: point.y
    });
    await delay(120);
    await client.send("Input.dispatchMouseEvent", {
      type: "mousePressed",
      x: point.x,
      y: point.y,
      button: "left",
      buttons: 1,
      clickCount: 1
    });
    await delay(90);
    await client.send("Input.dispatchMouseEvent", {
      type: "mouseReleased",
      x: point.x,
      y: point.y,
      button: "left",
      buttons: 0,
      clickCount: 1
    });
  }

  // Button positions come from GameEntry.buildShell: the layout uses
  // view.getVisibleSize(), so these are offsets from the centre.
  const visible = (await designToPage(0, 0)).visible;
  const bottom = -visible.height / 2 + 62;

  await shot("01-menu");

  await clickNode("LoginButton");
  await delay(6000);
  await shot("02-world");

  await clickNode("EnterLevelButton");
  await delay(5000);
  await shot("03-room");

  await clickDesign(60, 0);
  await delay(2000);
  await shot("04-room-moved");

  // Echo only reaches two units of level space, so walk to the hidden object
  // before casting; a cast from the spawn point is refused by design (the
  // server compares against the player's authoritative position, not the tap).
  // Tapping the marker itself sets the walk target to that exact point, which
  // works at any canvas size - the old version used page pixels tuned to a
  // 1280-wide canvas and simply missed the room on a phone.
  // ROOM-01 draws its markers as "HiddenObject" / "LightMarker" / "ExitGate".
  await clickNode("HiddenObject");
  await delay(6000);
  await shot("04b-room-near-hidden");

  // "回声 · 显形" casts RULE_ECHO at the hidden object; the pulse sprite only
  // exists during the tween, so the screenshot has to be taken immediately.
  await clickNode("RoomEchoButton");
  await delay(900);
  await shot("05-echo-cast");

  writeFileSync(`${outDir}/console.log`, consoleLines.join("\n"));
  console.log(consoleLines.slice(-30).join("\n") || "(no console output)");
  chrome.kill();
  process.exit(0);
}

main().catch((error) => {
  console.error(error);
  chrome.kill();
  process.exit(1);
});
