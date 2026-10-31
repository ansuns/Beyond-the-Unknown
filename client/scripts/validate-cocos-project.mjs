import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const root = process.cwd();
const read = async (path) => readFile(resolve(root, path), "utf8");
const fail = (message) => {
  console.error(`Cocos project validation failed: ${message}`);
  process.exitCode = 1;
};

try {
  const pkg = JSON.parse(await read("package.json"));
  const version = (await read(".cocos-version")).trim();
  if (version !== "3.8.8" || pkg.creatorVersion !== version) {
    fail(`expected Cocos Creator 3.8.8, got .cocos-version=${version}, package.creatorVersion=${pkg.creatorVersion}`);
  }

const BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/**
 * Compress a script uuid into the class id a scene actually stores.
 *
 * Cocos resolves a component by this id, not by the asset uuid. Writing the raw
 * uuid into the scene looks right and silently loses the component at load
 * ("component ... is corrupted"), which is exactly what happened before.
 */
function compressUuid(uuid) {
  const hex = uuid.replace(/-/g, "");
  let out = hex.slice(0, 5);
  for (let index = 5; index < 32; index += 3) {
    const chunk = Number.parseInt(hex.slice(index, index + 3), 16);
    out += BASE64[(chunk >> 6) & 63] + BASE64[chunk & 63];
  }
  return out;
}

  const scene = JSON.parse(await read("assets/scenes/Boot.scene"));
  const sceneMeta = JSON.parse(await read("assets/scenes/Boot.scene.meta"));
  const scriptMeta = JSON.parse(await read("assets/scripts/engine/GameEntry.ts.meta"));
  const entrySource = await read("assets/scripts/engine/GameEntry.ts");

  if (sceneMeta.uuid !== scene.find((item) => item.__type__ === "cc.Scene")?._id) {
    fail("Boot.scene metadata UUID does not match serialized cc.Scene ID");
  }
  if (!entrySource.includes('@ccclass("BeyondTheUnknownGameEntry")')) {
    fail("GameEntry.ts does not register the expected Cocos component class");
  }
  const classId = compressUuid(scriptMeta.uuid);
  if (!scene.some((item) => item.__type__ === classId)) {
    fail(
      `Boot.scene does not reference the GameEntry class id (${classId}); ` +
        "the engine resolves components by the compressed id, not the asset uuid"
    );
  }
  if (!scene.some((item) => item.__type__ === "cc.Camera")) {
    fail("Boot.scene has no camera component");
  }
  if (!scene.some((item) => item.__type__ === "cc.SceneAsset")) {
    fail("Boot.scene has no SceneAsset root");
  }

  const importPaths = [...entrySource.matchAll(/from\s+["'](\.\.?\/[^"']+)["']/g)]
    .map((match) => match[1]);
  for (const importPath of importPaths) {
    const base = resolve(root, "assets/scripts/engine", importPath);
    let found = false;
    for (const candidate of [base + ".ts", resolve(base, "index.ts")]) {
      try {
        await readFile(candidate);
        found = true;
        break;
      } catch {
        // Try the next supported TypeScript module resolution candidate.
      }
    }
    if (!found) fail(`unresolved local TypeScript import: ${importPath}`);
  }

  console.log("Cocos Creator 3.8.8 project metadata, Boot scene, component UUID and local imports are valid.");
} catch (error) {
  fail(error instanceof Error ? error.message : String(error));
}
