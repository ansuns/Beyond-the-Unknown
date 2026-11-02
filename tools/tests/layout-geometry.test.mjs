// Tests for the landscape geometry checks.
//
// These are synthetic node trees, not engine runs: the point is to prove each
// check catches its own failure mode and does not get fooled by a lookalike.
// `node --test tools/tests/layout-geometry.test.mjs`

import assert from "node:assert/strict";
import test from "node:test";

import {
  coveredFraction,
  detectCoveredTargets,
  detectOverflows,
  detectOverlaps,
  detectSafeAreaViolations,
  detectTouchConflicts,
  minVisualSize,
  visualSize
} from "../lib/layout-geometry.mjs";

function rect(name, left, bottom, right, top, extra = {}) {
  return { name, left, bottom, right, top, kind: "graphics", ...extra };
}

const VISIBLE = { width: 960, height: 443 };

test("overflow catches a control that leaves the screen but ignores one that merely touches the edge", () => {
  const nodes = [
    rect("Title", -400, 190, 400, 210),
    rect("Offside", 300, -100, 520, -80)
  ];
  const found = detectOverflows(nodes, VISIBLE);
  assert.deepEqual(found.map((item) => item.name), ["Offside"]);
  // 520 - 480 = 40 design units past the right edge; the 1 px tolerance only
  // decides whether it counts, not how far out it is.
  assert.equal(Math.round(found[0].over_right), 40);
});

test("two controls can both be inside the visible area and still collide", () => {
  const inside = [
    rect("RulesStatus", -200, -60, 200, -40, { kind: "label" }),
    rect("EnterLevelButton", -60, -70, 60, -30, { kind: "button" })
  ];
  assert.equal(detectOverflows(inside, VISIBLE).length, 0, "nothing should overflow");

  const overlaps = detectOverlaps(inside);
  assert.equal(overlaps.length, 1);
  assert.equal(overlaps[0].a, "RulesStatus");
  assert.ok(overlaps[0].covered_fraction_of_smaller >= 0.5, "half the smaller control is buried");
});

test("a one-pixel border touch is not reported as an overlap", () => {
  const touching = [
    rect("ProgressButton", -110, 0, -10, 40, { kind: "button" }),
    rect("CharacterButton", -10.5, 0, 90, 40, { kind: "button" })
  ];
  assert.deepEqual(detectOverlaps(touching), []);
});

test("full-surface nodes are excluded so the backdrop does not bury everything", () => {
  const nodes = [
    rect("Background", -480, -222, 480, 222, { kind: "graphics" }),
    rect("WorldViewport", -450, -100, 450, 100, { kind: "graphics" }),
    rect("Status", -300, 190, 300, 210, { kind: "label" })
  ];
  const overlaps = detectOverlaps(nodes);
  assert.deepEqual(overlaps, [], "nothing should be compared against the backdrop");
});

test("touch conflicts name the node that loses the tap", () => {
  const nodes = [
    rect("VirtualJoystick", -460, -220, -340, -100, { kind: "touch", touchTarget: true }),
    rect("LoginButton", -400, -200, -300, -120, { kind: "button" })
  ];
  const conflicts = detectTouchConflicts(nodes);
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].shadowed, "VirtualJoystick");
  assert.equal(conflicts[0].shadowing, "LoginButton");
  assert.ok(conflicts[0].shadowed_covered > 0.3);
});

test("an interactive object under the HUD is reported once it is materially covered", () => {
  const targets = [rect("HiddenObject", -20, -20, 20, 20, { kind: "sprite" })];
  const occluders = [
    rect("RoomEchoButton", -100, 0, 60, 40, { kind: "button" }),
    rect("Unrelated", 300, 300, 360, 340, { kind: "button" })
  ];
  const covered = detectCoveredTargets(targets, occluders, { threshold: 0.25 });
  assert.equal(covered.length, 1);
  assert.equal(covered[0].covered_by, "RoomEchoButton");
  assert.ok(covered[0].covered_fraction >= 0.25);

  // Below the threshold it is decoration touching the edge, not something hidden.
  assert.deepEqual(detectCoveredTargets(targets, occluders, { threshold: 0.9 }), []);
});

test("coveredFraction measures the target, not the occluder", () => {
  const big = rect("Backdrop", -500, -500, 500, 500);
  const small = rect("Knob", -4, -4, 4, 4);
  assert.equal(coveredFraction(small, big), 1);
  assert.ok(coveredFraction(big, small) < 0.001);
});

test("the smallest rendered control is reported in canvas pixels", () => {
  const nodes = [
    rect("Title", -400, 200, 400, 230),
    rect("Player", -6, -6, 6, 6)
  ];
  const worst = minVisualSize(nodes, 0.9);
  assert.equal(worst.name, "Player");
  assert.equal(worst.width_px, 10.8);
  assert.equal(worst.height_px, 10.8);
  assert.deepEqual(visualSize(nodes[0], 2), { width_px: 1600, height_px: 60 });
});

test("a button flush against the edge fails the safe-area check while one inset passes", () => {
  const nodes = [
    rect("EmoteButton", 480 - 88, 190, 480, 220, { kind: "button" }),
    rect("ProgressButton", -470, 100, -382, 130, { kind: "button" })
  ];
  const violations = detectSafeAreaViolations(nodes, VISIBLE, 8);
  assert.deepEqual(violations.map((item) => item.name), ["EmoteButton"]);
  assert.ok(violations[0].right_gap < 8);
});

test("a target's own container does not count as covering it", () => {
  const target = rect("HiddenObject", -10, -10, 10, 10, { kind: "sprite", path: "WorldViewport/Room01Prototype/HiddenObject" });
  const container = rect("WorldViewport", -450, -120, 450, 120, { kind: "container", path: "WorldViewport" });
  assert.equal(detectCoveredTargets([target], [container], { threshold: 0.2 }).length, 0);

  // A sibling drawn later still does.
  const button = rect("RoomEchoButton", -100, 0, 60, 40, { kind: "button", path: "RoomEchoButton" });
  const covered = detectCoveredTargets([target], [button], { threshold: 0.2 });
  assert.equal(covered.length, 1);
  assert.equal(covered[0].covered_by, "RoomEchoButton");
});

test("the joystick sitting over the map can be declared intentional, unlike button-on-button", () => {
  const nodes = [
    rect("WorldViewport", -450, -120, 450, 120, { kind: "touch", touchTarget: true }),
    rect("VirtualJoystick", -460, -220, -340, -100, { kind: "touch", touchTarget: true }),
    rect("LoginButton", -400, -200, -300, -120, { kind: "button" })
  ];
  const accepted = [["WorldViewport", "VirtualJoystick"]];
  const conflicts = detectTouchConflicts(nodes, { accepted });
  assert.equal(conflicts.length, 2);
  const joystick = conflicts.find((item) => item.shadowing === "VirtualJoystick");
  const button = conflicts.find((item) => item.shadowing === "LoginButton");
  assert.equal(joystick.intentional, true);
  assert.equal(button.intentional, false, "a button landing on the map is still a defect");
});

test("the art backdrop is not compared against the HUD drawn on top of it", () => {
  const nodes = [
    rect("ArtBackground", -450, -120, 450, 120, { kind: "sprite" }),
    rect("RoomTitle", -200, 90, 200, 120, { kind: "label" })
  ];
  assert.deepEqual(detectOverlaps(nodes), []);
});

test("a button and the label it owns are not reported as overlapping each other", () => {
  const nodes = [
    rect("EnterLevelButton", -95, -70, 95, -10, { kind: "button", path: "EnterLevelButton" }),
    rect("EnterLevelButtonLabel", -95, -70, 95, -10, { kind: "label", path: "EnterLevelButton/EnterLevelButtonLabel" })
  ];
  const overlaps = detectOverlaps(nodes);
  assert.deepEqual(overlaps, [], "a control always contains its own caption");
});

test("overlap severity separates a buried control from two objects brushing", () => {
  const nodes = [
    rect("Status", -300, -20, 300, 10, { kind: "label", path: "Status" }),
    rect("RulesStatus", -300, -25, 300, 5, { kind: "label", path: "RulesStatus" })
  ];
  const [overlap] = detectOverlaps(nodes);
  assert.equal(overlap.severity, "blocking");

  const brushing = [
    rect("ExitGate", 0, 0, 30, 30, { kind: "sprite", path: "Room/ExitGate" }),
    rect("ArtMechanism", 24, 0, 54, 30, { kind: "sprite", path: "Room/ArtMechanism" })
  ];
  const [minor] = detectOverlaps(brushing);
  assert.equal(minor.severity, "minor");
});

test("a surface yields taps to whatever is drawn on top of it", () => {
  const nodes = [
    rect("WorldViewport", -450, -120, 450, 120, { kind: "touch", touchTarget: true }),
    rect("RoomEchoButton", -100, 0, 60, 40, { kind: "button" })
  ];
  const [conflict] = detectTouchConflicts(nodes);
  assert.equal(conflict.intentional, true, "the map gives way to buttons over it");

  const twoButtons = [
    rect("RoomEchoButton", -100, 0, 60, 40, { kind: "button" }),
    rect("RoomExitButton", 20, 0, 180, 40, { kind: "button" })
  ];
  const [real] = detectTouchConflicts(twoButtons);
  assert.equal(real.intentional, false, "two buttons on top of each other is always a defect");
});
