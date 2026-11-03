// Drive the real WeChat DevTools simulator over its automation port.
//
// Two things about this environment, both learned the hard way:
//
// 1. The automation port only lives while an IDE opened with `cli open` is still
//    running. `cli auto` hands back a port number that means nothing once the
//    IDE exits, so keep the IDE alive in another shell:
//      cli.bat open --project <build> --port 9420          (leave running)
//      cli.bat auto --project <build> --auto-port 9423 --trust-project --port 9420
//
// 2. `miniprogram-automator@0.13.0` cannot use that port: its bundled ws@6
//    client never gets a reply, and `connect()` dies on `Tool.getInfo` with
//    "timeout waiting for automator response" while the same call over the
//    platform WebSocket answers in milliseconds. So the protocol is spoken
//    directly here (App.callFunction / App.captureScreenshot / Tool.getInfo).
//
// Everything reported comes from inside the running mini game: the bundle list
// is read from `cc.assetManager`, and `wx.loadSubpackage` is wrapped *before*
// the first input so a call can be observed rather than inferred.
const fs = require("fs");
const path = require("path");

const wsEndpoint = process.argv[2] || "ws://127.0.0.1:9423";
const outDir = process.argv[3] || "build/wxverify";
fs.mkdirSync(outDir, { recursive: true });

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const log = (...args) => console.log("[probe]", ...args);

class Client {
  constructor(ws) {
    this.ws = ws;
    this.nextId = 1;
    this.pending = new Map();
    this.consoleLines = [];
    ws.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
      } else if (message.method) {
        // Console/log pushes are best-effort; never let one fail the run.
        try {
          this.consoleLines.push({ method: message.method, params: message.params });
        } catch {}
      }
    });
  }

  call(method, params = {}, timeoutMs = 20000) {
    const id = `probe-${this.nextId++}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, {
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        }
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(fn, ...args) {
    const result = await this.call("App.callFunction", {
      functionDeclaration: fn.toString(),
      args
    });
    return result && Object.prototype.hasOwnProperty.call(result, "result")
      ? result.result
      : result;
  }

  async screenshot(file) {
    const response = await this.call("App.captureScreenshot", {}, 30000);
    if (!response || !response.data) throw new Error("empty screenshot payload");
    fs.writeFileSync(file, Buffer.from(response.data, "base64"));
    return fs.statSync(file).size;
  }
}

function connect() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(wsEndpoint);
    const timer = setTimeout(() => reject(new Error(`no websocket to ${wsEndpoint}`)), 10000);
    ws.addEventListener("open", () => {
      clearTimeout(timer);
      resolve(new Client(ws));
    });
    ws.addEventListener("error", (event) => {
      clearTimeout(timer);
      reject(new Error(`websocket error: ${event.message || "unknown"}`));
    });
  });
}

async function main() {
  log("connecting", wsEndpoint);
  const client = await connect();
  log("connected");

  const info = await client.call("Tool.getInfo");
  log("devtools", JSON.stringify(info));

  const env = await client.evaluate(() => ({
    hasCc: typeof cc !== "undefined",
    engineVersion: typeof cc !== "undefined" ? cc.ENGINE_VERSION : null,
    hasWx: typeof wx !== "undefined",
    hasLoadSubpackage: typeof wx !== "undefined" && typeof wx.loadSubpackage === "function",
    sceneName:
      typeof cc !== "undefined" && cc.director.getScene() ? cc.director.getScene().name : null
  }));
  log("env", JSON.stringify(env));

  const shot = async (name) => {
    const file = path.join(outDir, `${name}.png`);
    try {
      const size = await client.screenshot(file);
      log(`screenshot ${name}.png ${size} bytes`);
      return file;
    } catch (error) {
      log(`screenshot ${name} failed: ${error.message}`);
      return null;
    }
  };

  const bundles = () =>
    client.evaluate(() => {
      if (typeof cc === "undefined" || !cc.assetManager || !cc.assetManager.bundles) return null;
      const map = cc.assetManager.bundles._map;
      return map ? Object.keys(map) : null;
    });

  const status = () =>
    client.evaluate(() => {
      if (typeof cc === "undefined") return null;
      const scene = cc.director.getScene();
      if (!scene) return null;
      const seek = (node) => {
        if (node.name === "Status") {
          const label = node.getComponent("cc.Label");
          return label ? label.string : null;
        }
        for (const child of node.children) {
          const hit = seek(child);
          if (hit !== null && hit !== undefined) return hit;
        }
        return null;
      };
      return seek(scene);
    });

  await shot("01-boot");
  const boot = { status: await status(), bundles: await bundles() };
  log("boot", JSON.stringify(boot));

  // Wrap before the first tap: a bundle already in memory never calls
  // loadSubpackage, and a call observed afterwards proves nothing.
  const hook = await client.evaluate(() => {
    if (typeof wx === "undefined" || typeof wx.loadSubpackage !== "function") {
      return { installed: false, reason: "wx.loadSubpackage missing" };
    }
    if (wx.__probeOriginalLoadSubpackage) return { installed: true, reused: true };
    wx.__probeOriginalLoadSubpackage = wx.loadSubpackage;
    wx.__probeLoadSubpackageCalls = [];
    wx.loadSubpackage = function (options) {
      const entry = {
        name: options && options.name,
        at: Date.now(),
        settled: false
      };
      wx.__probeLoadSubpackageCalls.push(entry);
      const wrapped = Object.assign({}, options, {
        success: (...args) => {
          entry.settled = true;
          entry.ok = true;
          entry.settledAt = Date.now();
          if (options && typeof options.success === "function") options.success(...args);
        },
        fail: (...args) => {
          entry.settled = true;
          entry.ok = false;
          entry.settledAt = Date.now();
          const error = args[0];
          entry.error = error && (error.errMsg || error.message || String(error));
          if (options && typeof options.fail === "function") options.fail(...args);
        }
      });
      return wx.__probeOriginalLoadSubpackage.call(wx, wrapped);
    };
    return { installed: true };
  });
  log("hook", JSON.stringify(hook));

  const tap = async (nodeName) => {
    const result = await client.evaluate((name) => {
      if (typeof cc === "undefined") return { ok: false, reason: "no cc" };
      const scene = cc.director.getScene();
      if (!scene) return { ok: false, reason: "no scene" };
      const find = (node) => {
        if (node.name === name) return node;
        for (const child of node.children) {
          const hit = find(child);
          if (hit) return hit;
        }
        return null;
      };
      const node = find(scene);
      if (!node) return { ok: false, reason: `node ${name} not found` };
      // Cocos buttons listen for NodeEventType.TOUCH_END ("touch-end") and the
      // handler ignores its argument, so emitting the event is equivalent to a
      // tap without any coordinate math tied to the window size.
      node.emit("touch-end", null);
      return { ok: true };
    }, nodeName);
    log("tap", nodeName, JSON.stringify(result));
    return result;
  };

  const calls = () =>
    client.evaluate(() => (typeof wx !== "undefined" ? wx.__probeLoadSubpackageCalls || [] : []));

  const phases = { boot };

  await tap("LoginButton");
  await delay(10000);
  phases.world = {
    status: await status(),
    bundles: await bundles(),
    loadSubpackageCalls: await calls()
  };
  await shot("02-world");

  await tap("EnterLevelButton");
  await delay(8000);
  phases.roomFirst = {
    status: await status(),
    bundles: await bundles(),
    loadSubpackageCalls: await calls()
  };
  await shot("03-room-first");

  await tap("RoomAbandonButton");
  await delay(4000);
  phases.afterLeave = { status: await status() };
  await shot("04-world-again");

  await tap("EnterLevelButton");
  await delay(7000);
  phases.roomSecond = {
    status: await status(),
    bundles: await bundles(),
    loadSubpackageCalls: await calls()
  };
  await shot("05-room-second");

  const report = { wsEndpoint, devtools: info, env, phases };
  const file = path.join(outDir, "runtime-probe.json");
  fs.writeFileSync(file, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  log("written", file);

  for (const [phase, data] of Object.entries(phases)) {
    log(
      `${phase.padEnd(11)} status=${JSON.stringify(data.status)} bundles=${JSON.stringify(data.bundles)}`
    );
  }
  const observed = phases.roomSecond.loadSubpackageCalls || [];
  log(
    "loadSubpackage observed:",
    JSON.stringify(
      observed.map((item) => ({
        name: item.name,
        ok: item.ok,
        ms: item.settled ? item.settledAt - item.at : null,
        error: item.error
      }))
    )
  );

  process.exit(0);
}

main().catch((error) => {
  console.error("[probe] failed:", error && error.stack ? error.stack : error);
  process.exit(1);
});
