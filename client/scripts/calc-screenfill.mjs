// Exact layout + projection math for the 5 required landscape viewports.
// Mirrors computeShellLayout (GameEntry.ts) and prototype-layout.ts.

const LABEL_BOX_EXTRA = 16;

function shellLayout(w, h) {
  const compact = h < 560;
  const pad = compact ? 10 : 16;
  const titleSize = compact ? 21 : 30;
  const titleBox = titleSize + LABEL_BOX_EXTRA;
  const statusSize = compact ? 12 : 16;
  const statusBox = statusSize + LABEL_BOX_EXTRA;
  const navHeight = compact ? 30 : 44;
  const progressSize = compact ? 11 : 13;
  const progressBox = progressSize + LABEL_BOX_EXTRA;
  const bottomHeight = compact ? 40 : 54;
  const rulesSize = compact ? 12 : 14;
  const rulesBox = rulesSize + LABEL_BOX_EXTRA;
  const hintSize = 13;
  const hintBox = hintSize + LABEL_BOX_EXTRA;
  const showHint = h >= 580;

  let top = h / 2 - pad;
  top -= titleBox;
  top -= statusBox + (compact ? 2 : 6);
  top -= navHeight + 2;
  top -= progressBox + (compact ? 2 : 6);
  const topLimit = top;

  let floor = -h / 2 + pad;
  if (showHint) floor += hintBox + 2;
  floor += bottomHeight + 2;
  floor += rulesBox + (compact ? 2 : 6);
  const bottomLimit = floor;

  const gap = compact ? 8 : 14;
  const available = Math.max(120, topLimit - bottomLimit);
  const worldHeight = Math.max(120, available - gap * 2);
  const worldY = bottomLimit + available / 2;
  const worldWidth = Math.max(160, w - pad * 2);
  return { worldWidth, worldHeight, worldY, compact, pad };
}

const BOUNDS = { minX: 0, maxX: 12, minY: 0, maxY: 8 };
const CX = (BOUNDS.minX + BOUNDS.maxX) / 2;
const CY = (BOUNDS.minY + BOUNDS.maxY) / 2;
const SPAN = (BOUNDS.maxX - BOUNDS.minX) + (BOUNDS.maxY - BOUNDS.minY);

function local(x, y) {
  const lx = x - CX, ly = y - CY;
  return { x: lx - ly, y: lx + ly }; // unit scale
}

function coverScale(ww, wh) {
  return Math.min(220, (Math.max(Math.max(160, ww - 48), Math.max(80, wh - 24)) / SPAN) * 1.06);
}

const MUST = [
  ["spawn", 1, 4],
  ["M01-HIDEABLE", 5, 4],
  ["M01-LIGHT", 7.5, 4],
  ["M01-EXIT", 10.5, 4],
];

const VIEWPORTS = [
  [1280, 720], [1560, 720], [844, 390], [926, 428], [932, 430],
];

const MARGIN = 24;

function report(w, h) {
  const L = shellLayout(w, h);
  const S = coverScale(L.worldWidth, L.worldHeight);
  const halfW = w / 2;
  const halfH = h / 2 - Math.abs(L.worldY); // symmetric-safe visible half height about the room centre
  const room = SPAN * S;
  const rows = [];
  let worst = { name: "", over: -Infinity };
  for (const [name, x, y] of MUST) {
    const p = local(x, y);
    const sx = p.x * S, sy = p.y * S;
    // screen position relative to room centre -> UI coords = worldY + sy
    const uiY = L.worldY + sy;
    const inside = Math.abs(sx) <= halfW - MARGIN && Math.abs(sy) <= halfH - MARGIN;
    const over = Math.max(Math.abs(sx) - (halfW - MARGIN), Math.abs(sy) - (halfH - MARGIN));
    if (over > worst.over) worst = { name, over };
    rows.push({ name, sx: +sx.toFixed(1), sy: +sy.toFixed(1), uiY: +uiY.toFixed(1), inside });
  }
  return { w, h, L, S: +S.toFixed(2), room: +room.toFixed(1), halfW, halfH: +halfH.toFixed(1), rows, worst };
}

console.log("viewport | worldW×worldH | worldY | S(cover) | roomSquare | halfW | halfH | spawnUIy | contentInside?");
for (const [w, h] of VIEWPORTS) {
  const r = report(w, h);
  const spawn = r.rows[0];
  console.log(
    `${w}×${h} | ${r.L.worldWidth}×${r.L.worldHeight.toFixed(0)} | ${r.L.worldY.toFixed(1)} | ${r.S} | ${r.room} | ${r.halfW} | ${r.halfH} | ${spawn.uiY} | ${r.rows.every(x=>x.inside) ? "YES" : "NO ("+r.worst.name+" over "+r.worst.over.toFixed(1)+")"}`
  );
}

console.log("\n--- content-fit clamp: max scale keeping every must-see point inside ---");
for (const [w, h] of VIEWPORTS) {
  const L = shellLayout(w, h);
  const halfW = w / 2 - MARGIN;
  const halfH = h / 2 - Math.abs(L.worldY) - MARGIN;
  let sMax = Infinity, bind = "";
  for (const [name, x, y] of MUST) {
    const p = local(x, y);
    if (Math.abs(p.x) > 1e-6) { const s = halfW / Math.abs(p.x); if (s < sMax) { sMax = s; bind = name+"·x"; } }
    if (Math.abs(p.y) > 1e-6) { const s = halfH / Math.abs(p.y); if (s < sMax) { sMax = s; bind = name+"·y"; } }
  }
  const cover = coverScale(L.worldWidth, L.worldHeight);
  const s = Math.min(cover, sMax);
  console.log(`${w}×${h}: coverS=${cover.toFixed(2)} contentS=${sMax.toFixed(2)} -> use=${s.toFixed(2)} room=${(SPAN*s).toFixed(0)} (band=${L.worldWidth.toFixed(0)}×${L.worldHeight.toFixed(0)}, fill=${(SPAN*s/L.worldWidth*100).toFixed(0)}% w) bind=${bind}`);
}
