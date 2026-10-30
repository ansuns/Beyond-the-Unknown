import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { validateLevelContentConfig } from "./level-content-contract.mjs";

const configPath = resolve(process.cwd(), "../docs/engineering/levels/levels.v1.json");
const config = JSON.parse(await readFile(configPath, "utf8"));
const errors = validateLevelContentConfig(config);

if (errors.length) {
  console.error("Level content validation failed:");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
console.log("Level content valid: five normal rooms, one hidden room, unique IDs, valid objectives and ordered hidden-route objective mapping.");
