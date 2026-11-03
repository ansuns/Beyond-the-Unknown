// Real screenshots of the Cocos web build, driven through Chromium at the
// acceptance viewports. This is actual engine output, not a re-render.
const PW = process.env.PW_PATH || 'C:/Users/SYANG/AppData/Local/npm-cache/_npx/e41f203b7505f1fb/node_modules/playwright';
const { chromium } = require(PW);
const fs = require('fs');
const path = require('path');

const LABEL_BOX_EXTRA = 16;
function shell(w, h) {
  const compact = h < 560;
  const pad = compact ? 10 : 16;
  const titleBox = (compact ? 21 : 30) + LABEL_BOX_EXTRA;
  const statusBox = (compact ? 12 : 16) + LABEL_BOX_EXTRA;
  const navHeight = compact ? 30 : 44;
  const progressBox = (compact ? 11 : 13) + LABEL_BOX_EXTRA;
  const bottomHeight = compact ? 40 : 54;
  const bottomWidth = compact ? 140 : 190;
  const bottomSideWidth = compact ? 150 : 210;
  const rulesBox = (compact ? 12 : 14) + LABEL_BOX_EXTRA;
  const hintBox = 13 + LABEL_BOX_EXTRA;
  const showHint = h >= 580;

  let top = h / 2 - pad;
  top -= titleBox;
  top -= statusBox + (compact ? 2 : 6);
  top -= navHeight + 2;
  top -= progressBox + (compact ? 2 : 6);
  const topLimit = top;

  let floor = -h / 2 + pad;
  if (showHint) floor += hintBox + 2;
  const bottomY = floor + bottomHeight / 2;
  floor += bottomHeight + 2;
  floor += rulesBox + (compact ? 2 : 6);
  const bottomLimit = floor;
  void topLimit; void bottomLimit;
  return { pad, bottomY, bottomWidth, bottomSideWidth, bottomHeight };
}

const VIEWPORTS = [
  [1280, 720],
  [1560, 720],
  [844, 390],
  [926, 428],
  [932, 430],
];

const OUT = path.resolve(__dirname, '../docs/screenshots');
fs.mkdirSync(OUT, { recursive: true });

const only = process.argv[2]; // e.g. "1280x720"

(async () => {
  const browser = await chromium.launch({
    channel: 'chrome',
    headless: true,
    args: ['--enable-unsafe-swiftshader', '--use-gl=angle', '--use-angle=swiftshader'],
  });
  const errors = [];
  for (const [w, h] of VIEWPORTS) {
    if (only && only !== `${w}x${h}`) continue;
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`${w}x${h} console: ${m.text()}`); });
    page.on('pageerror', (e) => errors.push(`${w}x${h} pageerror: ${e.message}`));
    await page.goto('http://127.0.0.1:7456/index.html', { waitUntil: 'load', timeout: 60000 });
    // Wait for the Cocos canvas to exist and the first frame to draw.
    await page.waitForSelector('canvas', { timeout: 30000 });
    await page.waitForTimeout(6000);
    const tag = `${w}x${h}`;
    await page.screenshot({ path: path.join(OUT, `${tag}-1-login.png`) });

    const L = shell(w, h);
    const loginX = L.bottomSideWidth / 2 + L.pad;
    const loginY = h / 2 - L.bottomY;
    await page.mouse.click(loginX, loginY);
    await page.waitForTimeout(4500);
    await page.screenshot({ path: path.join(OUT, `${tag}-2-world.png`) });

    // Enter the personal level (ROOM-01) via the centre bottom button.
    const enterX = w / 2;
    const enterY = h / 2 - L.bottomY;
    await page.mouse.click(enterX, enterY);
    await page.waitForTimeout(4500);
    await page.screenshot({ path: path.join(OUT, `${tag}-3-room.png`) });

    console.log(`${tag}: clicked login(${loginX.toFixed(0)},${loginY.toFixed(0)}) enter(${enterX.toFixed(0)},${enterY.toFixed(0)})`);
    await ctx.close();
  }
  await browser.close();
  if (errors.length) {
    console.log('--- errors (' + errors.length + ') ---');
    console.log([...new Set(errors)].slice(0, 20).join('\n'));
  } else {
    console.log('no console/page errors');
  }
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
