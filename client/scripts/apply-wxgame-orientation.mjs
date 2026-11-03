// Formal build post-process: force landscape into the wechatgame game.json.
// Usage: node scripts/apply-wxgame-orientation.mjs [path/to/game.json]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ensureLandscape, isLandscape } from "./wxgame-orientation.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const target = process.argv[2] || path.resolve(here, "../build/wechatgame/game.json");

if (!fs.existsSync(target)) {
  console.error(`[orientation] game.json not found: ${target}`);
  process.exit(1);
}

const raw = fs.readFileSync(target, "utf8");
let gameJson;
try {
  gameJson = JSON.parse(raw);
} catch (error) {
  console.error(`[orientation] invalid JSON: ${error.message}`);
  process.exit(1);
}

if (isLandscape(gameJson)) {
  console.log(`[orientation] already landscape: ${target}`);
  process.exit(0);
}

const fixed = ensureLandscape(gameJson);
fs.writeFileSync(target, `${JSON.stringify(fixed, null, 4)}\n`);
const verify = JSON.parse(fs.readFileSync(target, "utf8"));
if (!isLandscape(verify)) {
  console.error("[orientation] failed to enforce landscape");
  process.exit(1);
}
console.log(`[orientation] ${target} -> landscape`);
