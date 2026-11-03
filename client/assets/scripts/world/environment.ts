// Full-screen fantasy backdrop for the landscape requirement.
//
// The world/room used to sit on a flat-colour rectangle, which read as "a small
// map in the centre with void around it". This paints a coherent environment -
// vertical gradient, a soft central glow, a faint grid, drifting motes and a
// vignette - so the area outside the room floor is scene content, never a bare
// edge. It is drawn on the Background node and extends beyond the viewport so a
// notch / safe-area inset or a resize never exposes a hard boundary.
//
// Pure of engine state (only Graphics + Color are imported) so it is also unit
// testable without a running scene.

import { Color, Graphics } from "cc";

export interface EnvironmentTheme {
  /** Top-to-bottom vertical gradient stops. t: 0 = top of screen, 1 = bottom. */
  stops: Array<{ t: number; color: [number, number, number] }>;
  glow: [number, number, number];
  grid: [number, number, number];
  vignette: [number, number, number];
  particle: [number, number, number];
}

export const DEFAULT_ENVIRONMENT: EnvironmentTheme = {
  stops: [
    { t: 0.0, color: [15, 24, 46] },
    { t: 0.42, color: [18, 38, 62] },
    { t: 1.0, color: [7, 14, 27] }
  ],
  glow: [48, 100, 136],
  grid: [44, 76, 104],
  vignette: [3, 7, 14],
  particle: [150, 196, 224]
};

function mix(a: [number, number, number], b: [number, number, number], t: number): Color {
  return new Color(
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
    255
  );
}

function sampleStops(stops: EnvironmentTheme["stops"], t: number): Color {
  const first = stops[0];
  if (t <= first.t) return new Color(first.color[0], first.color[1], first.color[2], 255);
  const last = stops[stops.length - 1];
  if (t >= last.t) return new Color(last.color[0], last.color[1], last.color[2], 255);
  for (let i = 0; i < stops.length - 1; i += 1) {
    const a = stops[i];
    const b = stops[i + 1];
    if (t >= a.t && t <= b.t) return mix(a.color, b.color, (t - a.t) / (b.t - a.t));
  }
  return new Color(last.color[0], last.color[1], last.color[2], 255);
}

// Deterministic pseudo-random in [0,1) from an integer index, so the backdrop is
// identical across redraws and a resize never flickers the motes.
function hash01(n: number): number {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

export function paintEnvironment(
  g: Graphics,
  width: number,
  height: number,
  theme: EnvironmentTheme = DEFAULT_ENVIRONMENT
): void {
  g.clear();
  const hw = width / 2;
  const hh = height / 2;

  // 1) Vertical gradient, drawn as fine bands (Graphics has no gradient fill).
  const BANDS = 64;
  for (let i = 0; i < BANDS; i += 1) {
    const t0 = i / BANDS;
    const t1 = (i + 1) / BANDS;
    g.fillColor = sampleStops(theme.stops, (t0 + t1) / 2);
    const y0 = -hh + t0 * height;
    const y1 = -hh + t1 * height;
    g.rect(-hw, y0, width, y1 - y0 + 1);
    g.fill();
  }

  // 2) Soft central glow (translucent concentric circles).
  const maxR = Math.max(hw, hh);
  const STEPS = 16;
  for (let i = STEPS; i >= 1; i -= 1) {
    const r = (maxR * i) / STEPS;
    const a = Math.round(46 * (1 - i / STEPS) * 0.5);
    g.fillColor = new Color(theme.glow[0], theme.glow[1], theme.glow[2], a);
    g.circle(0, 0, r);
    g.fill();
  }

  // 3) Faint grid so the backdrop reads as a space, not a flat fill.
  g.lineWidth = 1;
  g.strokeColor = new Color(theme.grid[0], theme.grid[1], theme.grid[2], 24);
  const step = 64;
  for (let x = -hw; x <= hw; x += step) {
    g.moveTo(x, -hh);
    g.lineTo(x, hh);
  }
  for (let y = -hh; y <= hh; y += step) {
    g.moveTo(-hw, y);
    g.lineTo(hw, y);
  }
  g.stroke();

  // 4) Drifting motes (deterministic positions/sizes).
  for (let i = 0; i < 26; i += 1) {
    const px = (hash01(i * 2 + 1) * 2 - 1) * hw * 0.96;
    const py = (hash01(i * 2 + 2) * 2 - 1) * hh * 0.96;
    const rad = 1 + hash01(i * 7 + 3) * 2.2;
    g.fillColor = new Color(theme.particle[0], theme.particle[1], theme.particle[2], 70);
    g.circle(px, py, rad);
    g.fill();
  }

  // 5) Vignette: darken the four edges so the centre holds the eye.
  const V = 10;
  for (let i = 0; i < V; i += 1) {
    const k = i / V;
    const a = Math.round(40 * (1 - k));
    g.fillColor = new Color(theme.vignette[0], theme.vignette[1], theme.vignette[2], a);
    const insetY = hh * k;
    g.rect(-hw, hh - insetY - 1, width, 2);
    g.rect(-hw, -hh + insetY, width, 2);
    const insetX = hw * k;
    g.rect(-hw + insetX, -hh, 2, height);
    g.rect(hw - insetX - 1, -hh, 2, height);
    g.fill();
  }
}
