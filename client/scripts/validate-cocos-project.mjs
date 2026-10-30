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
  if (!scene.some((item) => item.__type__ === scriptMeta.uuid)) {
    fail("Boot.scene does not reference the GameEntry script UUID");
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
