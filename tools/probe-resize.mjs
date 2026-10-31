// Read the HUD's real rectangles before and after a live resize.
//
// Screenshots of a resized page are hard to argue with and easy to misread: a
// stale compositor frame and a wrongly laid out HUD look the same. This prints
// the world-space boxes the touch dispatcher actually hit-tests against, so a
// button left off the edge shows up as a number outside the viewport.
//
// Usage: node tools/probe-resize.mjs <url>

import { setTimeout as delay } from "node:timers/promises";

import { connectPage, launchChrome } from "./lib/cdp.mjs";

const [url] = process.argv.slice(2);
if (!url) {
  console.error("usage: node tools/probe-resize.mjs <url>");
  process.exit(2);
}

const PORT = 9346;

const PROBE = `
  const cc = window.cc;
  if (!cc) return { error: 'cc missing' };
  const view = cc.view;
  const size = view.getVisibleSize();
  const canvas = cc.director.getScene().getChildByName('RuntimeCanvas');
  const runtime = canvas && canvas.getChildByName('BeyondTheUnknownRuntime');
  if (!runtime) return { error: 'runtime missing' };
  const names = ['Title','Status','ProgressSummary','RulesStatus','WorldViewport',
    'LoginButton','EnterLevelButton','ReturnButton','ProgressButton','CharacterButton','EmoteButton'];
  const boxes = [];
  for (const name of names) {
    const node = runtime.getChildByName(name);
    if (!node || !node.active) continue;
    const transform = node.getComponent('cc.UITransform');
    if (!transform) continue;
    const box = transform.getBoundingBoxToWorld();
    boxes.push({
      name,
      left: Math.round(box.xMin), right: Math.round(box.xMax),
      bottom: Math.round(box.yMin), top: Math.round(box.yMax)
    });
  }
  return {
    visible: { w: Math.round(size.width), h: Math.round(size.height) },
    design: (() => { const d = view.getDesignResolutionSize(); return { w: d.width, h: d.height }; })(),
    boxes
  };
`;

function report(label, probe) {
  if (probe.error) {
    console.log(`${label}: ERROR ${probe.error}`);
    return;
  }
  const halfW = probe.visible.w / 2;
  const halfH = probe.visible.h / 2;
  console.log(`${label}: visible ${probe.visible.w}x${probe.visible.h}, design ${probe.design.w}x${probe.design.h}`);
  for (const box of probe.boxes) {
    const out =
      box.left < -halfW - 0.5 ||
      box.right > halfW + 0.5 ||
      box.bottom < -halfH - 0.5 ||
      box.top > halfH + 0.5;
    console.log(
      `   ${out ? "OUT " : "    "}${box.name.padEnd(18)} x[${box.left},${box.right}] y[${box.bottom},${box.top}]`
    );
  }
}

const chrome = await launchChrome(PORT, { width: 1280, height: 720 });
const client = await connectPage(PORT);

try {
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: 1280,
    height: 720,
    deviceScaleFactor: 1,
    mobile: false
  });
  await client.send("Page.navigate", { url });
  await delay(4500);

  report("before resize", await client.evaluate(PROBE));

  await client.send("Emulation.setDeviceMetricsOverride", {
    width: 844,
    height: 390,
    deviceScaleFactor: 1,
    mobile: true
  });
  await delay(1800);
  report("after  resize", await client.evaluate(PROBE));
} finally {
  client.ws.close();
  chrome.kill();
}
