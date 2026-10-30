import { access, readFile } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve } from "node:path";

const manifestPath = resolve(process.cwd(), "../docs/engineering/assets/asset-manifest.v1.json");
const levelConfigPath = resolve(process.cwd(), "../docs/engineering/levels/levels.v1.json");
const strict = process.argv.includes("--strict");
const errors = [];
const add = (message) => errors.push(message);

const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const levelConfig = JSON.parse(await readFile(levelConfigPath, "utf8"));

if (manifest.schema_version !== 1) add("asset manifest schema_version must be 1");
if (manifest.gdd_version !== "0.2") add("asset manifest GDD baseline must be 0.2");
if (!Array.isArray(manifest.entries)) add("entries must be an array");

const expectedCharacters = Array.from({ length: 12 }, (_, index) =>
  `CHR_${String(index + 1).padStart(3, "0")}`,
);
if (JSON.stringify(manifest.character_ids) !== JSON.stringify(expectedCharacters)) {
  add("manifest must include exactly CHR_001 through CHR_012 in order");
}
const expectedLevels = levelConfig.levels.map((level) => level.level_id);
if (JSON.stringify(manifest.level_ids) !== JSON.stringify(expectedLevels)) {
  add("manifest level_ids do not match levels.v1.json");
}

const ids = new Set();
const counts = new Map();
for (const entry of manifest.entries ?? []) {
  if (!entry.asset_id || ids.has(entry.asset_id)) add(`missing or duplicate asset_id: ${entry.asset_id}`);
  ids.add(entry.asset_id);
  counts.set(entry.status, (counts.get(entry.status) ?? 0) + 1);
  if (!["MISSING", "IN_PROGRESS", "READY", "BLOCKED"].includes(entry.status)) {
    add(`${entry.asset_id}: invalid status ${entry.status}`);
  }
  if (entry.required !== true) add(`${entry.asset_id}: MVP manifest entry must be required`);
  if (!entry.expected_directory || entry.expected_directory.startsWith("/") || entry.expected_directory.split("/").includes("..")) {
    add(`${entry.asset_id}: expected_directory must be a safe client-relative path`);
  }
  if (!Array.isArray(entry.files)) add(`${entry.asset_id}: files must be an array`);
  if (entry.status === "READY" && (entry.files?.length ?? 0) === 0) {
    add(`${entry.asset_id}: READY requires at least one delivered file`);
  }
  for (const file of entry.files ?? []) {
    if (file.startsWith("/") || file.split("/").includes("..")) {
      add(`${entry.asset_id}: unsafe file path ${file}`);
      continue;
    }
    try {
      await access(resolve(process.cwd(), file), constants.R_OK);
    } catch {
      add(`${entry.asset_id}: declared file does not exist: ${file}`);
    }
  }
  if (strict && entry.required && entry.status !== "READY") {
    add(`${entry.asset_id}: release blocker status=${entry.status}`);
  }
}

const expectedMechanisms = new Set(
  levelConfig.levels.flatMap((level) => level.mechanisms.map((mechanism) => mechanism.mechanism_id)),
);
const manifestMechanisms = new Set(
  (manifest.entries ?? []).filter((entry) => entry.category === "mechanism").map((entry) => entry.asset_id),
);
for (const id of expectedMechanisms) if (!manifestMechanisms.has(id)) add(`mechanism asset missing from manifest: ${id}`);
for (const id of manifestMechanisms) if (!expectedMechanisms.has(id)) add(`orphan mechanism asset in manifest: ${id}`);
for (const category of ["character_portrait", "character_model", "character_preview", "character_animation", "main_map", "level_geometry", "mechanism", "effect", "ui", "audio"]) {
  if (!(manifest.entries ?? []).some((entry) => entry.category === category)) add(`required asset category missing: ${category}`);
}

const total = manifest.entries?.length ?? 0;
console.log(`Asset manifest structurally valid: ${total} required entries; ${counts.get("READY") ?? 0} READY, ${counts.get("IN_PROGRESS") ?? 0} IN_PROGRESS, ${counts.get("MISSING") ?? 0} MISSING, ${counts.get("BLOCKED") ?? 0} BLOCKED.`);
if (!strict && (counts.get("MISSING") ?? 0) > 0) {
  console.log("Non-strict mode: missing assets are reported as tracked work, not treated as a CI failure.");
}
if (errors.length) {
  console.error("Asset manifest validation failed:");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
if (strict && total > 0 && counts.get("READY") !== total) process.exit(1);
