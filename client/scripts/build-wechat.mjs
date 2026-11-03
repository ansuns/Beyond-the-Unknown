// Reproducible WeChat mini-game build using the project's formal config.
//
// Cocos 3.8.8 loads a build config only via `configPath`, and that path must be
// ABSOLUTE (the builder rejects `project://...`). This script therefore:
//   1. cleans build/wechatgame-slim (so a stale artifact cannot mask a failure),
//   2. runs the editor with configPath=<abs path to build-configs/wechat-slim.json>,
//   3. turns every declared bundle into a real WeChat subpackage,
//   4. verifies the artifact (orientation, appid, entry files, subpackage layout),
//   5. forces landscape only if the config did not already emit it.
// Editor path override: COCOS_CREATOR.
//
// Two things here were learned the hard way and must not be "simplified":
//
// A. Success is judged by the artifact, not by the editor's exit status. The
//    editor is an Electron GUI: it exits 36 when its OTA check fails even after
//    a clean build, and on some runs it does not exit at all. Waiting on that
//    process hung this script for nine minutes once. So the build is considered
//    done when the log prints the finish marker AND the artifact stops growing,
//    and the editor is then terminated deliberately.
//
// B. The subpackage move is done here because the platform plugin does not do
//    it. Measured: `packages.wechatgame.subpackages` makes the plugin write the
//    declaration into game.json, but it does NOT move `assets/<bundle>` and does
//    NOT register the bundle in `settings.assets.subpackages`. The artifact then
//    claims a subpackage whose root directory does not exist, while the runtime
//    keeps loading the bundle from the main package. `bundles[].isSubpackage`
//    (which the vivo / oppo plugins honour) is ignored by this plugin, and
//    `bundleConfigs` is a whitelist that drops every unlisted bundle - including
//    the built-in `resources`. Every one of those outcomes was reproduced.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { ensureLandscape, isLandscape } from "./wxgame-orientation.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const project = path.resolve(here, "..");
const editor = process.env.COCOS_CREATOR || "C:\\ProgramData\\cocos\\editors\\Creator\\3.8.8\\CocosCreator.exe";
const configPath = path.resolve(project, "build-configs/wechat-slim.json");
const outDir = path.resolve(project, "build/wechatgame-slim");
const logPath = path.resolve(project, "build", "wechat-build.log");
const gameJsonPath = path.join(outDir, "game.json");
const projectConfigPath = path.join(outDir, "project.config.json");

const BUILD_TIMEOUT_MS = 10 * 60 * 1000;
const ARTIFACT_STABLE_MS = 4000;

// WeChat refuses to compile a subpackage whose root has no game.js entry.
// A bundle of assets has no code to run, so the entry is an inert stub; Cocos
// loads the bundle by reading config.<version>.json itself.
const SUBPACKAGE_ENTRY = [
  "// WeChat requires a game.js entry in every subpackage root.",
  "// This bundle ships assets only; Cocos loads it via assetManager.loadBundle.",
  ""
].join("\n");

if (!fs.existsSync(editor)) {
  console.error(`[build:wechat] Cocos editor not found: ${editor} (set COCOS_CREATOR)`);
  process.exit(1);
}
if (!fs.existsSync(configPath)) {
  console.error(`[build:wechat] build config not found: ${configPath}`);
  process.exit(1);
}

const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
const outputName = config.outputName ?? "wechatgame-slim";
const finishMarker = new RegExp(`build Task \\(${outputName}\\) Finished`);

// Clean the controlled output dir so we never mistake an old artifact for a new one.
fs.rmSync(outDir, { recursive: true, force: true });
if (fs.existsSync(outDir)) {
  console.error(`[build:wechat] could not clean ${outDir}`);
  process.exit(1);
}
fs.mkdirSync(path.dirname(logPath), { recursive: true });
console.log(`[build:wechat] config: ${configPath}`);
console.log(`[build:wechat] output: ${outDir}`);

/** A cheap fingerprint of the artifact: names and sizes, not hashes. */
function artifactSignature(dir) {
  if (!fs.existsSync(dir)) return "";
  const parts = [];
  for (const entry of fs.readdirSync(dir, { recursive: true })) {
    const file = path.join(dir, entry);
    try {
      const stat = fs.statSync(file);
      if (stat.isFile()) parts.push(`${entry}:${stat.size}`);
    } catch {
      // A file that vanished mid-scan is exactly why a second look happens.
    }
  }
  return parts.sort().join("|");
}

/** Entries whose presence means the builder got far enough to be worth checking. */
function artifactComplete(dir) {
  const required = ["game.js", "game.json", "project.config.json", "assets", "src"];
  if (!required.every((name) => fs.existsSync(path.join(dir, name)))) return false;
  const src = path.join(dir, "src");
  return fs.readdirSync(src).some((name) => /^settings.*\.json$/.test(name));
}

function killEditorTree(pid) {
  if (!pid) return;
  // The editor spawns build workers that outlive it on Windows; a plain kill
  // leaves them holding the project directory.
  spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
}

async function runBuild() {
  // ELECTRON_RUN_AS_NODE makes the editor behave as node and reject --project.
  const env = { ...process.env };
  delete env.ELECTRON_RUN_AS_NODE;
  delete env.NODE_OPTIONS;

  // The editor's output goes to a file instead of an inherited pipe: workers it
  // spawns inherit that pipe and keep it open, which is what made `| tail`
  // block forever even after the build had finished.
  const logFd = fs.openSync(logPath, "w");
  const child = spawn(
    editor,
    ["--project", project, "--build", `configPath=${configPath}`],
    { env, stdio: ["ignore", logFd, logFd] }
  );

  const startedAt = Date.now();
  let lastSignature = "";
  let stableSince = 0;
  let finishedByLog = false;
  let exited = false;
  child.on("exit", () => {
    exited = true;
  });

  while (Date.now() - startedAt < BUILD_TIMEOUT_MS) {
    await delay(1000);

    let logText = "";
    try {
      logText = fs.readFileSync(logPath, "utf8");
    } catch {
      // Log not flushed yet.
    }
    if (finishMarker.test(logText)) finishedByLog = true;

    const signature = artifactSignature(outDir);
    const complete = artifactComplete(outDir);
    if (complete && signature === lastSignature) {
      if (!stableSince) stableSince = Date.now();
      // Two independent signals, because either one alone has lied:
      // the marker can print before the last file is flushed, and a stable
      // directory can be a stalled build.
      else if (finishedByLog || Date.now() - stableSince >= ARTIFACT_STABLE_MS) break;
    } else {
      lastSignature = signature;
      stableSince = 0;
    }
  }

  if (!exited) {
    console.warn("[build:wechat] editor did not exit on its own; terminating it");
    killEditorTree(child.pid);
    await delay(1500);
  }
  fs.closeSync(logFd);

  if (!artifactComplete(outDir)) {
    const tail = fs.existsSync(logPath) ? fs.readFileSync(logPath, "utf8").slice(-2000) : "";
    console.error(`[build:wechat] the build did not produce a complete artifact in ${outDir}`);
    console.error(`[build:wechat] last log lines:\n${tail}`);
    process.exit(1);
  }
}

await runBuild();

/** The settings file name carries a build hash, so it cannot be hard-coded. */
function findSettings(dir) {
  const src = path.join(dir, "src");
  const file = fs.readdirSync(src).find((name) => /^settings.*\.json$/.test(name));
  if (!file) throw new Error(`no src/settings*.json in ${dir}`);
  return path.join(src, file);
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeJson(file, value) {
  fs.writeFileSync(file, `${JSON.stringify(value, null, 4)}\n`);
}

/**
 * Move one bundle out of the main package and register it as a subpackage.
 *
 * Every step is asserted afterwards by `verifySubpackage`, because each of these
 * has shipped broken at least once: the directory left behind in `assets/`
 * (double-shipped), the declaration missing from game.json (WeChat never
 * downloads it), the registration missing from settings (the runtime keeps
 * asking the main package), and the bundle left in preloadBundles (downloaded
 * before the first tap).
 */
function makeSubpackage(dir, { name, root }) {
  const normalizedRoot = `${root.replace(/\/+$/, "")}/`;
  const source = path.join(dir, "assets", name);
  const target = path.join(dir, normalizedRoot);

  if (fs.existsSync(source)) {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.rmSync(target, { recursive: true, force: true });
    fs.renameSync(source, target);
    console.log(`[build:wechat] moved assets/${name} -> ${normalizedRoot}`);
  } else if (!fs.existsSync(target)) {
    throw new Error(`bundle ${name} exists neither in assets/ nor ${normalizedRoot}`);
  }

  const entry = path.join(target, "game.js");
  if (!fs.existsSync(entry)) fs.writeFileSync(entry, SUBPACKAGE_ENTRY, "utf8");

  const game = readJson(gameJsonPath);
  const declarations = (game.subpackages ?? []).filter((item) => item.name !== name);
  declarations.push({ name, root: normalizedRoot });
  game.subpackages = declarations;
  writeJson(gameJsonPath, game);

  const settingsPath = findSettings(dir);
  const settings = readJson(settingsPath);
  settings.assets = settings.assets ?? {};
  const registered = new Set(settings.assets.subpackages ?? []);
  registered.add(name);
  settings.assets.subpackages = [...registered];
  settings.assets.preloadBundles = (settings.assets.preloadBundles ?? []).filter(
    (item) => item.bundle !== name
  );
  fs.writeFileSync(settingsPath, JSON.stringify(settings));

  return { name, root: normalizedRoot };
}

/** Throw unless the artifact really is a subpackage, not a declaration of one. */
function verifySubpackage(dir, { name, root }) {
  const target = path.join(dir, root);
  const problems = [];

  if (!fs.existsSync(target)) {
    problems.push(`${root} does not exist`);
  } else {
    const files = fs
      .readdirSync(target, { recursive: true })
      .filter((item) => fs.statSync(path.join(target, item)).isFile());
    if (files.length === 0) problems.push(`${root} is empty`);
    if (!files.some((item) => /^config\..+\.json$/.test(path.basename(item)))) {
      problems.push(`${root} has no config.<version>.json`);
    }
    if (!files.some((item) => path.basename(item) === "game.js")) {
      problems.push(`${root} has no game.js entry`);
    }
  }

  if (fs.existsSync(path.join(dir, "assets", name))) {
    problems.push(`assets/${name} still exists: the bundle is shipped twice`);
  }

  const declared = (readJson(gameJsonPath).subpackages ?? []).find((item) => item.name === name);
  if (!declared) problems.push(`game.json does not declare ${name}`);
  else if (declared.root.replace(/\/+$/, "") !== root.replace(/\/+$/, "")) {
    problems.push(`game.json root ${declared.root} != ${root}`);
  }

  const settings = readJson(findSettings(dir));
  const registered = settings.assets?.subpackages ?? [];
  if (!registered.includes(name)) {
    problems.push(`settings.assets.subpackages does not register ${name}`);
  }
  const preloaded = (settings.assets?.preloadBundles ?? []).some((item) => item.bundle === name);
  if (preloaded) problems.push(`${name} is still in preloadBundles: it downloads before the first tap`);

  if (problems.length) {
    for (const problem of problems) console.error(`[build:wechat] subpackage FAIL: ${problem}`);
    process.exit(1);
  }
}

const declarations = config.packages?.wechatgame?.subpackages ?? [];
const built = declarations.map((declaration) => makeSubpackage(outDir, declaration));
for (const subpackage of built) verifySubpackage(outDir, subpackage);

const gameJson = readJson(gameJsonPath);
if (!isLandscape(gameJson)) {
  writeJson(gameJsonPath, ensureLandscape(gameJson));
  console.warn("[build:wechat] config did not emit landscape; forced it");
}
const verifiedGame = readJson(gameJsonPath);
if (!isLandscape(verifiedGame)) {
  console.error("[build:wechat] game.json is not landscape");
  process.exit(1);
}

const projectConfig = readJson(projectConfigPath);
const expectedAppId = config?.packages?.wechatgame?.appid;
if (expectedAppId && projectConfig.appid !== expectedAppId) {
  console.error(`[build:wechat] appid mismatch: ${projectConfig.appid} != ${expectedAppId}`);
  process.exit(1);
}

console.log("[build:wechat] manifest:");
console.log(`  orientation=${verifiedGame.deviceOrientation}`);
console.log(`  appid=${projectConfig.appid}`);
console.log(`  subpackages=${JSON.stringify(verifiedGame.subpackages ?? [])}`);
for (const subpackage of built) {
  const dir = path.join(outDir, subpackage.root);
  const bytes = fs
    .readdirSync(dir, { recursive: true })
    .map((item) => path.join(dir, item))
    .filter((item) => fs.statSync(item).isFile())
    .reduce((sum, item) => sum + fs.statSync(item).size, 0);
  console.log(`  ${subpackage.name}: ${subpackage.root} ${(bytes / 1024).toFixed(0)} KB`);
}
console.log("[build:wechat] OK");
