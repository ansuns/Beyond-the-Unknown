// Fix the two pieces of the generated index.html that CSS cannot reach.
//
// The web-desktop template ships:
//   <meta name="viewport" content="..."> with no viewport-fit, so phones with a
//   notch inset the page instead of letting it run under the cutout;
//   <meta name="screen-orientation" content="portrait"> on a landscape game,
//   which makes some mobile browsers and in-app webviews lock the page upright.
//
// A build-templates/web-desktop/index.html would fix both, but only by replacing
// the whole file - including the script tags the editor generates, whose names
// change when md5Cache is on. Patching the generated file keeps the editor in
// charge of the script list and only rewrites the two attributes.
//
// Usage: node tools/patch-web-shell.mjs <build-dir>

import { readFileSync, writeFileSync } from "node:fs";

const [buildDir] = process.argv.slice(2);
if (!buildDir) {
  console.error("usage: node tools/patch-web-shell.mjs <build-dir>");
  process.exit(2);
}

const file = `${buildDir}/index.html`;
const original = readFileSync(file, "utf8");

const patches = [
  {
    // The game is landscape (game.json says so for the mini game), so the page
    // it lives in must not ask for portrait.
    from: /<meta name="screen-orientation" content="portrait"\/?>/,
    to: '<meta name="screen-orientation" content="landscape"/>'
  },
  {
    // viewport-fit=cover lets the canvas run under the notch and rounded
    // corners; without it iOS letterboxes the page inside the safe area, which
    // is the one thing a "fill the screen" build must not do.
    from: /content="width=device-width,user-scalable=no,initial-scale=1,minimum-scale=1,maximum-scale=1,minimal-ui=true"/,
    to: 'content="width=device-width,user-scalable=no,initial-scale=1,minimum-scale=1,maximum-scale=1,minimal-ui=true,viewport-fit=cover"'
  }
];

let patched = original;
const applied = [];
for (const patch of patches) {
  if (!patch.from.test(patched)) {
    // Loud, not silent: a template change would otherwise leave the fix behind
    // with nothing to show for it.
    console.error(`patch target not found in ${file}: ${patch.from}`);
    process.exit(1);
  }
  patched = patched.replace(patch.from, patch.to);
  applied.push(patch.to.slice(0, 60));
}

if (patched === original) {
  console.log("web shell already patched");
} else {
  writeFileSync(file, patched);
  for (const item of applied) console.log(`patched: ${item}`);
}
