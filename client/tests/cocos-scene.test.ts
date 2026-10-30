import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const sceneUrl = new URL("../assets/scenes/Boot.scene", import.meta.url);
const scriptMetaUrl = new URL("../assets/scripts/engine/GameEntry.ts.meta", import.meta.url);
const packageUrl = new URL("../package.json", import.meta.url);
const engineVersionUrl = new URL("../.cocos-version", import.meta.url);

describe("Cocos Creator Boot scene assets", () => {
  it("keeps the scene JSON parseable and links its entry component to the script UUID", () => {
    const scene = JSON.parse(readFileSync(sceneUrl, "utf8")) as Array<Record<string, unknown>>;
    const scriptMeta = JSON.parse(readFileSync(scriptMetaUrl, "utf8")) as { uuid: string };

    expect(scene[0]?.__type__).toBe("cc.SceneAsset");
    expect(scene[0]?._name).toBe("Boot");
    expect(scene.some((asset) => asset.__type__ === scriptMeta.uuid)).toBe(true);
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
