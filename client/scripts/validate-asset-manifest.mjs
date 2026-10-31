import { access, readFile } from "node:fs/promises";
import { constants } from "node:fs";
import { resolve } from "node:path";
import { validateAssetManifestStructure } from "./asset-manifest-contract.mjs";

const manifestPath = resolve(process.cwd(), "../docs/engineering/assets/asset-manifest.v1.json");
const levelConfigPath = resolve(process.cwd(), "../docs/engineering/levels/levels.v1.json");
const strict = process.argv.includes("--strict");
const manifest = JSON.parse(await readFile(manifestPath, "utf8"));
const levelConfig = JSON.parse(await readFile(levelConfigPath, "utf8"));
const result = validateAssetManifestStructure(manifest, levelConfig, strict);
const errors = [...result.errors];

for (const entry of manifest.entries ?? []) {
  if (entry.status === "READY") {
    for (const field of ["license_evidence", "acceptance_evidence"]) {
      const evidencePath = entry.provenance?.[field];
      try {
        await access(resolve(process.cwd(), "..", evidencePath), constants.R_OK);
      } catch {
        errors.push(`${entry.asset_id}: provenance.${field} file does not exist: ${evidencePath ?? ""}`);
      }
    }
  }
  for (const file of entry.files ?? []) {
    try {
      await access(resolve(process.cwd(), file), constants.R_OK);
    } catch {
      errors.push(`${entry.asset_id}: declared file does not exist: ${file}`);
    }
  }
}

console.log(
  `Asset manifest: ${result.total} required entries; ${result.counts.READY} READY, ${result.counts.IN_PROGRESS} IN_PROGRESS, ${result.counts.MISSING} MISSING, ${result.counts.BLOCKED} BLOCKED.`
);
if (!strict && result.counts.MISSING > 0) {
  console.log("Non-strict mode: missing assets are tracked work, not treated as a CI failure.");
}
if (errors.length) {
  console.error("Asset manifest validation failed:");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
if (strict && result.total > 0 && result.counts.READY !== result.total) process.exit(1);
