import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const sceneUrl = new URL("../assets/scenes/Boot.scene", import.meta.url);
const scriptMetaUrl = new URL("../assets/scripts/engine/GameEntry.ts.meta", import.meta.url);
const packageUrl = new URL("../package.json", import.meta.url);
const engineVersionUrl = new URL("../.cocos-version", import.meta.url);

const BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/**
 * Compress a script UUID the way Cocos names a script class.
 *
 * The scene stores the class id, not the asset uuid, and the two are easy to
 * confuse: writing the full uuid looks correct in the file and silently loses
 * the component at load time ("component ... is corrupted"). Keeping the
 * conversion here means the test fails loudly if the scene ever stores the
 * wrong form again.
 */
function compressUuid(uuid: string): string {
  const hex = uuid.replace(/-/g, "");
  if (hex.length !== 32) throw new Error(`not a uuid: ${uuid}`);
  let out = hex.slice(0, 5);
  for (let index = 5; index < 32; index += 3) {
    const chunk = Number.parseInt(hex.slice(index, index + 3), 16);
    out += BASE64[(chunk >> 6) & 63];
    out += BASE64[chunk & 63];
  }
  return out;
}

describe("Cocos Creator Boot scene assets", () => {
  it("compresses script uuids the way the engine does", () => {
    // Known pair from a build: the scene must carry the right-hand form.
    expect(compressUuid("8f7d9b13-3a54-4f75-9b83-0f7a7e9d8c31")).toBe(
      "8f7d9sTOlRPdZuDD3p+nYwx"
    );
  });

  it("links the entry component to the compressed script class id", () => {
    const scene = JSON.parse(readFileSync(sceneUrl, "utf8")) as Array<Record<string, unknown>>;
    const scriptMeta = JSON.parse(readFileSync(scriptMetaUrl, "utf8")) as { uuid: string };

    expect(scene[0]?.__type__).toBe("cc.SceneAsset");
    expect(scene[0]?._name).toBe("Boot");

    const classId = compressUuid(scriptMeta.uuid);
    expect(scene.some((asset) => asset.__type__ === classId)).toBe(true);
    // The raw uuid must not appear: that is the shape that broke the scene.
    expect(scene.some((asset) => asset.__type__ === scriptMeta.uuid)).toBe(false);
  });

  it("pins the Cocos editor version consistently", () => {
    const project = JSON.parse(readFileSync(packageUrl, "utf8")) as {
      creatorVersion?: string;
    };
    const engineVersion = readFileSync(engineVersionUrl, "utf8").trim();

    expect(project.creatorVersion).toBe("3.8.8");
    expect(engineVersion).toBe("3.8.8");
  });
});
