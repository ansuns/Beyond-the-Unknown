// Reproducible WeChat mini-game build:
//   1. run the Cocos Creator headless build (Electron mode),
//   2. enforce landscape in build/wechatgame/game.json (Cocos writes portrait),
//   3. verify the artifact declares landscape.
// Editor path can be overridden with COCOS_CREATOR.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ensureLandscape, isLandscape } from "./wxgame-orientation.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, "..");
const editor = process.env.COCOS_CREATOR || "C:\\ProgramData\\cocos\\editors\\Creator\\3.8.8\\CocosCreator.exe";
const gameJsonPath = path.resolve(project, "build/wechatgame/game.json");

if (!fs.existsSync(editor)) {
  console.error(`[build:wechat] Cocos editor not found: ${editor} (set COCOS_CREATOR)`);
  process.exit(1);
}

// The WorkBuddy shell exports ELECTRON_RUN_AS_NODE=1, which makes the editor
// behave as plain node and reject --project. Strip it for the child process.
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
delete env.NODE_OPTIONS;

console.log("[build:wechat] running Cocos wechatgame build...");
const startedAt = Date.now();
const result = spawnSync(
  editor,
  [
    "--project", project,
    "--build", "platform=wechatgame;debug=true;buildPath=build",
  ],
  { stdio: "inherit", env }
);
// The editor exits 36 when its OTA (login) check fails even though the local
// build finished. Trust the artifact, not the exit code: if game.json was
// written by this run, the build succeeded.
const built =
  fs.existsSync(gameJsonPath) && fs.statSync(gameJsonPath).mtimeMs >= startedAt - 2000;
if (!built) {
  console.error(`[build:wechat] Cocos build produced no game.json (editor exit ${result.status})`);
  process.exit(result.status || 1);
}
if (result.status !== 0) {
  console.warn(`[build:wechat] editor exited ${result.status} (non-fatal: artifact was written)`);
}

const gameJson = JSON.parse(fs.readFileSync(gameJsonPath, "utf8"));
if (!isLandscape(gameJson)) {
  fs.writeFileSync(gameJsonPath, `${JSON.stringify(ensureLandscape(gameJson), null, 4)}\n`);
  console.log("[build:wechat] forced deviceOrientation=landscape");
}
const verify = JSON.parse(fs.readFileSync(gameJsonPath, "utf8"));
if (!isLandscape(verify)) {
  console.error("[build:wechat] game.json still not landscape");
  process.exit(1);
}
console.log("[build:wechat] OK: build/wechatgame/game.json declares landscape");
