// Does the game actually fill the screen, or does it letterbox?
//
// "全是黑的" was the symptom; the cause was never measured. This tool answers
// the question with numbers instead of a screenshot that can be argued with:
//
//   windowCoverage - the canvas rect over the browser viewport. Below 1 the
//                    page itself has margins, a header, a footer or a border.
//   canvasUsage    - the engine's viewport rect over the canvas backing store.
//                    Below 1 the engine letterboxes: the design resolution does
//                    not match the screen aspect, so bars are drawn.
//   coverage       - their product: the fraction of the screen the game paints.
//
// It also reads the resolution policy and design size, because those are the
// two knobs that decide canvasUsage, and captures a screenshot per viewport so
// the numbers can be checked against pixels.
//
// Usage: node tools/verify-fullscreen.mjs <url> <outDir>

import { mkdirSync, writeFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";

import { connectPage, launchChrome } from "./lib/cdp.mjs";

const [url, outDir] = process.argv.slice(2);
if (!url || !outDir) {
  console.error("usage: node tools/verify-fullscreen.mjs <url> <outDir>");
  process.exit(2);
}

const PORT = 9344;
const VIEWPORTS = [
  { name: "desktop-1280x720", width: 1280, height: 720 },
  { name: "phone-16x9", width: 1280, height: 720 },
  { name: "phone-18x9", width: 1440, height: 720 },
  { name: "phone-19.5x9", width: 1560, height: 720 },
  { name: "phone-20x9", width: 1600, height: 720 },
  { name: "phone-844x390", width: 844, height: 390 }
];

// Runs inside the page. Reads the live view state, so it reports what the
// engine is doing right now rather than what the config file claims.
const PROBE = `
  const view = window.cc && window.cc.view;
  const canvas = document.getElementById('GameCanvas') || document.querySelector('canvas');
  if (!canvas) return { error: 'no canvas' };
  const rect = canvas.getBoundingClientRect();
  const gameDiv = document.getElementById('GameDiv');
  const divRect = gameDiv ? gameDiv.getBoundingClientRect() : null;
  const vr = view ? view.getViewportRect() : null;
  const vs = view ? view.getVisibleSize() : null;
  const ds = view ? view.getDesignResolutionSize() : null;
  const policy = view && view.getResolutionPolicy ? view.getResolutionPolicy() : null;
  return {
    dpr: window.devicePixelRatio,
    inner: { w: window.innerWidth, h: window.innerHeight },
    client: { w: document.documentElement.clientWidth, h: document.documentElement.clientHeight },
    canvasRect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
    canvasBacking: { w: canvas.width, h: canvas.height },
    gameDivRect: divRect ? { x: divRect.x, y: divRect.y, w: divRect.width, h: divRect.height } : null,
    viewportRect: vr ? { x: vr.x, y: vr.y, w: vr.width, h: vr.height } : null,
    visibleSize: vs ? { w: vs.width, h: vs.height } : null,
    designSize: ds ? { w: ds.width, h: ds.height } : null,
    policy: policy ? (policy._id ?? policy.constructor?.name ?? String(policy)) : null,
    scale: view ? { x: view.getScaleX(), y: view.getScaleY() } : null,
    bodyBg: getComputedStyle(document.body).backgroundColor,
    bodyMargin: getComputedStyle(document.body).margin
  };
`;

// The rectangles the touch dispatcher hit-tests against. A screenshot of a
// resized page can be a stale compositor frame, so the resize check reads these
// instead of trusting pixels: a control laid out for the old width shows up as
// a box outside the new viewport.
const BOX_PROBE = `
  const cc = window.cc;
  if (!cc) return { error: 'cc missing' };
  const view = cc.view;
  const size = view.getVisibleSize();
  const canvas = cc.director.getScene().getChildByName('RuntimeCanvas');
  const runtime = canvas && canvas.getChildByName('BeyondTheUnknownRuntime');
  if (!runtime) return { error: 'runtime missing' };
  const names = ['Title','Status','ProgressSummary','RulesStatus','WorldViewport',
    'LoginButton','EnterLevelButton','ReturnButton','ProgressButton','CharacterButton',
    'EmoteButton','VirtualJoystick'];
  const boxes = [];
  for (const name of names) {
    const node = runtime.getChildByName(name);
    if (!node || !node.active) continue;
    const transform = node.getComponent('cc.UITransform');
    if (!transform) continue;
    const box = transform.getBoundingBoxToWorld();
    boxes.push({
      name,
      left: box.xMin, right: box.xMax, bottom: box.yMin, top: box.yMax
    });
  }
  return {
    visible: { w: size.width, h: size.height },
    design: (() => { const d = view.getDesignResolutionSize(); return { w: d.width, h: d.height }; })(),
    boxes
  };
`;

function overflowBoxes(probe, tolerance = 0.5) {
  if (probe.error) return [`probe error: ${probe.error}`];
  const halfW = probe.visible.w / 2;
  const halfH = probe.visible.h / 2;
  return probe.boxes
    .filter(
      (box) =>
        box.left < -halfW - tolerance ||
        box.right > halfW + tolerance ||
        box.bottom < -halfH - tolerance ||
        box.top > halfH + tolerance
    )
    .map((box) => `${box.name} x[${Math.round(box.left)},${Math.round(box.right)}] y[${Math.round(box.bottom)},${Math.round(box.top)}]`);
}

function round(value, digits = 3) {
  if (typeof value !== "number" || !Number.isFinite(value)) return value;
  const factor = 10 ** digits;
  return Math.round(value * factor) / factor;
}

function analyse(probe) {
  const { inner, canvasRect, canvasBacking, viewportRect, dpr } = probe;
  const windowArea = inner.w * inner.h;
  const canvasArea = canvasRect.w * canvasRect.h;
  const windowCoverage = windowArea > 0 ? canvasArea / windowArea : 0;

  // The engine draws inside viewportRect (device pixels). Anything of the
  // backing store outside it is left untouched - the letterbox.
  const backingArea = canvasBacking.w * canvasBacking.h;
  const viewportArea = viewportRect ? viewportRect.w * viewportRect.h : backingArea;
  const canvasUsage = backingArea > 0 ? viewportArea / backingArea : 0;

  // Bars in CSS pixels, so they can be compared against the viewport directly.
  const bars = viewportRect
    ? {
        left: round(viewportRect.x / dpr),
        bottom: round(viewportRect.y / dpr),
        right: round((canvasBacking.w - viewportRect.x - viewportRect.w) / dpr),
        top: round((canvasBacking.h - viewportRect.y - viewportRect.h) / dpr)
      }
    : null;

  return {
    windowCoverage: round(windowCoverage),
    canvasUsage: round(canvasUsage),
    coverage: round(windowCoverage * canvasUsage),
    barsCssPx: bars,
    letterboxed: round(windowCoverage * canvasUsage) < 0.999
  };
}

mkdirSync(outDir, { recursive: true });
const chrome = await launchChrome(PORT, { width: 1280, height: 720 });
const client = await connectPage(PORT);

try {
  await client.send("Page.enable");
  await client.send("Runtime.enable");

  const report = {
    url,
    generatedAt: new Date().toISOString(),
    tool: "tools/verify-fullscreen.mjs",
    viewports: []
  };

  for (const viewport of VIEWPORTS) {
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: viewport.width,
      height: viewport.height,
      deviceScaleFactor: 1,
      mobile: viewport.height < 600
    });
    await client.send("Page.navigate", { url });
    // The engine boots, loads main, then builds the shell. Rushing this reports
    // the loading screen's geometry instead of the game's.
    await delay(4500);

    const probe = await client.evaluate(PROBE);
    const shot = await client.send("Page.captureScreenshot", { format: "png" });
    writeFileSync(`${outDir}/${viewport.name}.png`, Buffer.from(shot.data, "base64"));

    report.viewports.push({
      name: viewport.name,
      requested: { width: viewport.width, height: viewport.height },
      probe,
      analysis: probe.error ? null : analyse(probe)
    });

    const line = probe.error
      ? `  ${viewport.name}: ERROR ${probe.error}`
      : `  ${viewport.name}: coverage=${analyse(probe).coverage} ` +
        `(canvas/window=${analyse(probe).windowCoverage}, ` +
        `engine/canvas=${analyse(probe).canvasUsage}) ` +
        `bars=${JSON.stringify(analyse(probe).barsCssPx)}`;
    console.log(line);
  }

  // Fitting at load is only half of it: a browser window gets resized after the
  // game is already running. Reloading at each size (above) would pass even if
  // nothing listened for a resize, so this one resizes the live page and
  // measures again without a navigation.
  await client.send("Emulation.setDeviceMetricsOverride", {
    width: 1280,
    height: 720,
    deviceScaleFactor: 1,
    mobile: false
  });
  await client.send("Page.navigate", { url });
  await delay(4500);
  const beforeResize = await client.evaluate(PROBE);

  await client.send("Emulation.setDeviceMetricsOverride", {
    width: 844,
    height: 390,
    deviceScaleFactor: 1,
    mobile: true
  });
  // The resize has to reach the page and the engine before this is measured.
  await delay(1500);
  const afterResize = await client.evaluate(PROBE);
  const boxesAfterResize = await client.evaluate(BOX_PROBE);
  const overflowAfterResize = overflowBoxes(boxesAfterResize);
  const shot = await client.send("Page.captureScreenshot", { format: "png" });
  writeFileSync(`${outDir}/resize-to-844x390.png`, Buffer.from(shot.data, "base64"));

  report.resize = {
    before: { probe: beforeResize, analysis: analyse(beforeResize) },
    after: { probe: afterResize, analysis: analyse(afterResize) },
    boxesAfterResize,
    overflowAfterResize
  };
  console.log(
    `  live resize 1280x720 -> 844x390: coverage=${analyse(beforeResize).coverage} -> ` +
      `${analyse(afterResize).coverage}, design ${beforeResize.designSize.w}x${beforeResize.designSize.h}` +
      ` -> ${afterResize.designSize.w}x${afterResize.designSize.h}, ` +
      `controls outside the new viewport: ${overflowAfterResize.length}`
  );
  for (const item of overflowAfterResize) console.log(`    OUT ${item}`);

  writeFileSync(`${outDir}/fullscreen.json`, JSON.stringify(report, null, 2));
  console.log(`\nwrote ${outDir}/fullscreen.json`);
} finally {
  client.ws.close();
  chrome.kill();
}
