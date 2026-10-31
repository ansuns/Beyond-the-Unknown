// Pure geometry checks for the landscape layout.
//
// Overflow alone proved to be a weak check: every control can sit inside the
// visible area and the layout can still be unusable, because two controls can
// overlap, a button can cover the marker you are supposed to tap, or the player
// can shrink to twenty pixels. These functions take the rectangles the engine
// reports and answer each question separately, so the report cannot collapse
// four different failures into one PASS.

export const INTERACTIVE_KINDS = new Set(["button", "touch"]);

/**
 * Rectangles are axis-aligned in Cocos UI space: x grows right, y grows up,
 * the visible area is centred on the origin.
 */
export function overlapRect(a, b) {
  const width = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const height = Math.min(a.top, b.top) - Math.max(a.bottom, b.bottom);
  if (width <= 0 || height <= 0) return null;
  return { left: Math.max(a.left, b.left), right: Math.min(a.right, b.right), bottom: Math.max(a.bottom, b.bottom), top: Math.min(a.top, b.top) };
}

export function area(rect) {
  return (rect.right - rect.left) * (rect.top - rect.bottom);
}

/** How much of `rect` is covered by another rectangle, as a fraction. */
export function coveredFraction(target, other) {
  const hit = overlapRect(target, other);
  if (!hit) return 0;
  return area(hit) / Math.max(1, area(target));
}

/**
 * Classify a node so the checks can treat a full-screen backdrop differently
 * from a button: comparing the backdrop with everything reports 15 overlaps and
 * says nothing.
 */
export function classify(node) {
  if (node.getComponentLabel) return "label";
  if (node.name.endsWith("Button")) return "button";
  if (node.hasSprite) return "sprite";
  if (node.children && node.children.length) return "container";
  return "graphics";
}

// The shell backdrop, the canvas itself and the world viewport are surfaces the
// HUD is drawn on top of. Comparing anything against them reports an overlap
// that means nothing: everything is inside them by definition. ArtBackground is
// the map/room backdrop sprite, which likewise fills the surface it decorates.
const FULL_SURFACE = new Set([
  "Background",
  "RuntimeCanvas",
  "BeyondTheUnknownRuntime",
  "WorldViewport",
  "RoomRoot",
  "IsometricRoom",
  "ArtBackground"
]);

/** Containers and the backdrop are not "content" that another control can cover. */
export function isContent(node) {
  if (FULL_SURFACE.has(node.name)) return false;
  const kind = node.kind ?? classify(node);
  return kind === "label" || kind === "button" || kind === "sprite" || kind === "graphics";
}

export function detectOverflows(nodes, visible, tolerance = 1) {
  const halfW = visible.width / 2 + tolerance;
  const halfH = visible.height / 2 + tolerance;
  return nodes
    .filter((node) => node.right > halfW || node.left < -halfW || node.top > halfH || node.bottom < -halfH)
    .map((node) => ({
      name: node.name,
      over_left: +(node.left + visible.width / 2).toFixed(1),
      over_right: +(node.right - visible.width / 2).toFixed(1),
      over_top: +(node.top - visible.height / 2).toFixed(1),
      over_bottom: +(node.bottom + visible.height / 2).toFixed(1)
    }));
}

/**
 * Overlap between two content controls.
 *
 * `minFraction` is the share of the *smaller* control that must be covered: two
 * adjacent 40 px buttons sharing a single pixel of anti-aliased border is not a
 * layout defect, half a button under a label is.
 */
const BLOCKING_FRACTION = 0.25;

/** True when one node is drawn inside the other (a button and its own label). */
function related(a, b) {
  if (!a.path || !b.path) return false;
  return a.path.startsWith(`${b.path}/`) || b.path.startsWith(`${a.path}/`);
}

export function detectOverlaps(nodes, { minimalOverlapPx = 1, minFraction = 0.05 } = {}) {
  const content = nodes.filter(isContent);
  const found = [];
  for (let i = 0; i < content.length; i += 1) {
    for (let j = i + 1; j < content.length; j += 1) {
      const a = content[i];
      const b = content[j];
      // A button and the label it owns always share a rectangle; comparing them
      // buries the real findings under nine rows of noise.
      if (related(a, b)) continue;
      const hit = overlapRect(a, b);
      if (!hit) continue;
      const px = Math.min(area(hit), Math.min(area(a), area(b)));
      if (px < minimalOverlapPx) continue;
      const fraction = area(hit) / Math.min(area(a), area(b));
      if (fraction < minFraction) continue;
      found.push({
        a: a.name,
        b: b.name,
        kind_a: content[i].kind,
        kind_b: content[j].kind,
        overlap_px: +area(hit).toFixed(1),
        covered_fraction_of_smaller: +fraction.toFixed(3),
        // Two room objects brushing past each other is cosmetic; a control
        // buried halfway under another one is not.
        severity: fraction >= BLOCKING_FRACTION ? "blocking" : "minor"
      });
    }
  }
  return found.sort((x, y) => y.overlap_px - x.overlap_px);
}

/**
 * Touch areas that shadow each other.
 *
 * Cocos dispatches a tap to the topmost node whose rectangle contains the point,
 * so when two interactive rectangles intersect, the one drawn later silently
 * eats touches aimed at the earlier one.
 */
/**
 * Touch rectangles that shadow each other.
 *
 * `accepted` lists pairs that overlap on purpose - [shadowed, shadowing]. The
 * joystick has to sit over the map and take its own drags, otherwise moving
 * would also walk the player by tapping through it; that is a design decision,
 * while a button landing on another button never is.
 */
export function detectTouchConflicts(
  nodes,
  { minimalOverlapPx = 1, accepted = [], yieldingSurfaces = ["WorldViewport"] } = {}
) {
  const interactive = nodes.filter((node) => INTERACTIVE_KINDS.has(node.kind) || node.touchTarget);
  const found = [];
  for (let i = 0; i < interactive.length; i += 1) {
    for (let j = i + 1; j < interactive.length; j += 1) {
      const hit = overlapRect(interactive[i], interactive[j]);
      if (!hit || area(hit) < minimalOverlapPx) continue;
      const fractionA = coveredFraction(interactive[i], interactive[j]);
      const fractionB = coveredFraction(interactive[j], interactive[i]);
      const intentional =
        accepted.some(
          ([shadowed, shadowing]) =>
            shadowed === interactive[i].name && shadowing === interactive[j].name
        ) || yieldingSurfaces.includes(interactive[i].name);
      found.push({
        // Drawn later wins the tap, so the loser is the one that never receives it.
        shadowed: interactive[i].name,
        shadowing: interactive[j].name,
        intentional,
        overlap_px: +area(hit).toFixed(1),
        shadowed_covered: +fractionA.toFixed(3),
        shadowing_covered: +fractionB.toFixed(3)
      });
    }
  }
  return found.sort((x, y) => y.overlap_px - x.overlap_px);
}

/**
 * Is anything the player must tap hidden under the HUD?
 *
 * `occluders` are the nodes allowed to sit above the world (buttons, joystick,
 * labels); `targets` are the interactive things drawn inside it.
 */
export function detectCoveredTargets(targets, occluders, { threshold = 0.25 } = {}) {
  const found = [];
  for (const target of targets) {
    let worst = 0;
    let by = null;
    for (const occluder of occluders) {
      if (occluder.name === target.name) continue;
      // The node a target is drawn inside always covers 100% of it: the room
      // markers live under WorldViewport. Only siblings further up the draw
      // order can actually hide it from a tap.
      if (target.path && occluder.path && target.path.startsWith(`${occluder.path}/`)) continue;
      const fraction = coveredFraction(target, occluder);
      if (fraction > worst) {
        worst = fraction;
        by = occluder.name;
      }
    }
    if (worst >= threshold) {
      found.push({ target: target.name, covered_by: by, covered_fraction: +worst.toFixed(3) });
    }
  }
  return found.sort((a, b) => b.covered_fraction - a.covered_fraction);
}

/** Rendered size of a node in canvas pixels, given the design-unit scale. */
export function visualSize(node, pixelsPerUnit) {
  return {
    width_px: +(node.right - node.left) * pixelsPerUnit,
    height_px: +(node.top - node.bottom) * pixelsPerUnit
  };
}

export function minVisualSize(nodes, pixelsPerUnit) {
  let worst = null;
  for (const node of nodes) {
    const size = visualSize(node, pixelsPerUnit);
    const smaller = Math.min(size.width_px, size.height_px);
    if (!worst || smaller < worst.smaller_px) {
      worst = { name: node.name, smaller_px: +smaller.toFixed(2), ...size };
    }
  }
  return worst;
}

/**
 * Every interactive control has to keep a margin from the screen edge.
 *
 * The visible rectangle is not a safe area: on a phone the shell is drawn under
 * the rounded corners and WeChat's own capsule control overlaps the top-right
 * corner, so a button flush against an edge is unreachable rather than merely
 * ugly. `insetPx` is expressed in design units.
 */
export function detectSafeAreaViolations(nodes, visible, insetUnits = 8) {
  const halfW = visible.width / 2 - insetUnits;
  const halfH = visible.height / 2 - insetUnits;
  return nodes
    .filter((node) => (INTERACTIVE_KINDS.has(node.kind) || node.touchTarget) &&
      (node.left < -halfW || node.right > halfW || node.bottom < -halfH || node.top > halfH))
    .map((node) => ({
      name: node.name,
      left_gap: +(node.left + visible.width / 2).toFixed(1),
      right_gap: +(visible.width / 2 - node.right).toFixed(1),
      bottom_gap: +(node.bottom + visible.height / 2).toFixed(1),
      top_gap: +(visible.height / 2 - node.top).toFixed(1)
    }));
}
