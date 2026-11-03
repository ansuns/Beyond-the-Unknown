// Reproducible WeChat mini-game build using the project's formal config.
//
// Cocos 3.8.8 loads a build config only via `configPath`, and that path must be
// ABSOLUTE (the builder rejects `project://...`). This script therefore:
//   1. cleans build/wechatgame-slim (so a stale artifact cannot mask a failure),
//   2. runs the editor with configPath=<abs path to build-configs/wechat-slim.json>,
//   3. verifies the artifact manifest (orientation, appid, entry files, bundle dir),
//   4. forces landscape only if the config did not already emit it.
// Editor path override: COCOS_CREATOR.
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ensureLandscape, isLandscape } from "./wxgame-orientation.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, "..");
const editor = process.env.COCOS_CREATOR || "C:\\ProgramData\\cocos\\editors\\Creator\\3.8.8\\CocosCreator.exe";
const configPath = path.resolve(project, "build-configs/wechat-slim.json");
const outDir = path.resolve(project, "build/wechatgame-slim");
const gameJsonPath = path.join(outDir, "game.json");
const projectConfigPath = path.join(outDir, "project.config.json");

if (!fs.existsSync(editor)) {
  console.error(`[build:wechat] Cocos editor not found: ${editor} (set COCOS_CREATOR)`);
  process.exit(1);
}
if (!fs.existsSync(configPath)) {
  console.error(`[build:wechat] build config not found: ${configPath}`);
  process.exit(1);
}

// Clean the controlled output dir so we never mistake an old artifact for a new one.
fs.rmSync(outDir, { recursive: true, force: true });
if (fs.existsSync(outDir)) {
  console.error(`[build:wechat] could not clean ${outDir}`);
  process.exit(1);
}
console.log(`[build:wechat] config: ${configPath}`);
console.log(`[build:wechat] output: ${outDir}`);

// ELECTRON_RUN_AS_NODE makes the editor behave as node and reject --project.
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
delete env.NODE_OPTIONS;

const result = spawnSync(
  editor,
  ["--project", project, "--build", `configPath=${configPath}`],
  { stdio: "inherit", env }
);

// The editor exits 36 when its OTA/login check fails even after a local build.
// The cleaned output dir makes "artifact exists" a trustworthy success signal.
const REQUIRED = ["game.js", "game.json", "project.config.json", "cocos-js", "assets", "src"];
const missing = REQUIRED.filter((name) => !fs.existsSync(path.join(outDir, name)));
if (missing.length > 0) {
  console.error(`[build:wechat] missing artifact entries: ${missing.join(", ")} (editor exit ${result.status})`);
  process.exit(result.status || 1);
}
if (result.status !== 0) {
  console.warn(`[build:wechat] editor exited ${result.status} (non-fatal: artifact written)`);
}

const gameJson = JSON.parse(fs.readFileSync(gameJsonPath, "utf8"));
if (!isLandscape(gameJson)) {
  fs.writeFileSync(gameJsonPath, `${JSON.stringify(ensureLandscape(gameJson), null, 4)}\n`);
  console.warn("[build:wechat] config did not emit landscape; forced it");
}
const verifiedGame = JSON.parse(fs.readFileSync(gameJsonPath, "utf8"));
if (!isLandscape(verifiedGame)) {
  console.error("[build:wechat] game.json is not landscape");
  process.exit(1);
}

const projectConfig = JSON.parse(fs.readFileSync(projectConfigPath, "utf8"));
const expectedAppId = JSON.parse(fs.readFileSync(configPath, "utf8"))?.packages?.wechatgame?.appid;
if (expectedAppId && projectConfig.appid !== expectedAppId) {
  console.error(`[build:wechat] appid mismatch: ${projectConfig.appid} != ${expectedAppId}`);
  process.exit(1);
}

const bundleDir = path.join(outDir, "assets/resources");
console.log("[build:wechat] manifest:");
console.log(`  orientation=${verifiedGame.deviceOrientation}`);
console.log(`  appid=${projectConfig.appid}`);
console.log(`  subpackages=${JSON.stringify(verifiedGame.subpackages ?? [])}`);
console.log(`  resourcesBundle=${fs.existsSync(bundleDir) ? "present" : "absent"}`);
console.log("[build:wechat] OK");
