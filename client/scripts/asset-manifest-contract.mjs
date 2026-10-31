const CHARACTER_CATEGORIES = [
  ["PORTRAIT", "character_portrait"],
  ["MODEL", "character_model"],
  ["PREVIEW", "character_preview"],
  ["ANIMATION_SET", "character_animation"]
];

const MAIN_MAP_ASSETS = [
  ["SCENE", "main_map"],
  ["GROUND", "main_map"],
  ["PROPS", "main_map"],
  ["COLLISION", "main_map"],
  ["WALKABLE", "main_map"],
  ["SPAWN", "main_map"],
  ["ENTRANCES", "main_map"],
  ["CAMERA", "main_map"],
  ["CONFIG", "main_map"]
];

const EFFECT_IDS = [
  "FX_ECHO_PULSE_01",
  "FX_GAZE_BEAM_01",
  "FX_REVERSE_FLOW_01",
  "FX_ROOM_CLEAR_01",
  "FX_ROOM_CLEAR_02",
  "FX_ROOM_CLEAR_03",
  "FX_ROOM_CLEAR_04",
  "FX_ROOM_CLEAR_05",
  "FX_HIDDEN_ENDING"
];

const UI_IDS = [
  "UI_LOGIN",
  "UI_CHARACTER_SELECT",
  "UI_MAIN_MAP_HUD",
  "UI_INTERACTION",
  "UI_LAW_BAR",
  "UI_DISCOVERY",
  "UI_SETTLEMENT",
  "UI_LEADERBOARD",
  "UI_COLLECTION",
  "UI_REWARD",
  "UI_PROFILE",
  "UI_NETWORK_STATE"
];

const P0_ASSET_IDS = new Set([
  "CHR_001_PORTRAIT",
  "CHR_001_MODEL",
  "CHR_001_PREVIEW",
  "CHR_001_ANIMATION_SET",
  "MAP_MAIN_001_SCENE",
  "MAP_MAIN_001_GROUND",
  "MAP_MAIN_001_PROPS",
  "MAP_MAIN_001_COLLISION",
  "MAP_MAIN_001_WALKABLE",
  "MAP_MAIN_001_SPAWN",
  "MAP_MAIN_001_ENTRANCES",
  "MAP_MAIN_001_CAMERA",
  "MAP_MAIN_001_CONFIG",
  "LV-ROOM-01_GEOMETRY",
  "M01-EXIT-01",
  "M01-HIDEABLE-01",
  "M01-LIGHT-01",
  "FX_ECHO_PULSE_01",
  "FX_GAZE_BEAM_01",
  "FX_REVERSE_FLOW_01",
  "UI_LOGIN",
  "UI_MAIN_MAP_HUD",
  "UI_INTERACTION",
  "UI_LAW_BAR",
  "UI_SETTLEMENT",
  "UI_NETWORK_STATE",
  "AUD_UI_CLICK",
  "AUD_INTERACTION",
  "AUD_ECHO",
  "AUD_GAZE",
  "AUD_REVERSE",
  "AUD_DISCOVERY",
  "AUD_SETTLEMENT_CLEAR",
  "AUD_NETWORK_DISCONNECT",
  "AUD_NETWORK_RECONNECT",
  "AUD_BGM_MAIN_MAP",
  "AUD_BGM_ROOM"
]);
const P2_ASSET_IDS = new Set([
  "CHR_002_PORTRAIT",
  "CHR_002_MODEL",
  "CHR_002_PREVIEW",
  "CHR_002_ANIMATION_SET",
  "CHR_003_PORTRAIT",
  "CHR_003_MODEL",
  "CHR_003_PREVIEW",
  "CHR_003_ANIMATION_SET",
  "CHR_004_PORTRAIT",
  "CHR_004_MODEL",
  "CHR_004_PREVIEW",
  "CHR_004_ANIMATION_SET",
  "CHR_005_PORTRAIT",
  "CHR_005_MODEL",
  "CHR_005_PREVIEW",
  "CHR_005_ANIMATION_SET",
  "CHR_006_PORTRAIT",
  "CHR_006_MODEL",
  "CHR_006_PREVIEW",
  "CHR_006_ANIMATION_SET",
  "CHR_007_PORTRAIT",
  "CHR_007_MODEL",
  "CHR_007_PREVIEW",
  "CHR_007_ANIMATION_SET",
  "CHR_008_PORTRAIT",
  "CHR_008_MODEL",
  "CHR_008_PREVIEW",
  "CHR_008_ANIMATION_SET",
  "CHR_009_PORTRAIT",
  "CHR_009_MODEL",
  "CHR_009_PREVIEW",
  "CHR_009_ANIMATION_SET",
  "CHR_010_PORTRAIT",
  "CHR_010_MODEL",
  "CHR_010_PREVIEW",
  "CHR_010_ANIMATION_SET",
  "CHR_011_PORTRAIT",
  "CHR_011_MODEL",
  "CHR_011_PREVIEW",
  "CHR_011_ANIMATION_SET",
  "CHR_012_PORTRAIT",
  "CHR_012_MODEL",
  "CHR_012_PREVIEW",
  "CHR_012_ANIMATION_SET",
  "UI_CHARACTER_SELECT",
  "UI_DISCOVERY",
  "UI_LEADERBOARD",
  "UI_COLLECTION",
  "UI_REWARD",
  "UI_PROFILE",
  "AUD_SOCIAL_ACTION"
]);

const AUDIO_IDS = [
  "AUD_UI_CLICK",
  "AUD_INTERACTION",
  "AUD_ECHO",
  "AUD_GAZE",
  "AUD_REVERSE",
  "AUD_DISCOVERY",
  "AUD_SETTLEMENT_CLEAR",
  "AUD_SETTLEMENT_FAIL",
  "AUD_SOCIAL_ACTION",
  "AUD_NETWORK_DISCONNECT",
  "AUD_NETWORK_RECONNECT",
  "AUD_BGM_MAIN_MAP",
  "AUD_BGM_ROOM",
  "AUD_BGM_SETTLEMENT"
];

function isSafeEvidencePath(value) {
  return typeof value === "string" &&
    value.startsWith("docs/engineering/assets/evidence/") &&
    !value.startsWith("/") &&
    !value.split("/").includes("..") &&
    value.endsWith(".md");
}

function sameOrderedValues(actual, expected) {
  return Array.isArray(actual) && actual.length === expected.length &&
    actual.every((value, index) => value === expected[index]);
}

function addExpected(expected, id, category) {
  if (expected.has(id)) throw new Error(`duplicate expected asset ID: ${id}`);
  expected.set(id, category);
}

export function validateAssetManifestStructure(manifest, levelConfig, strict = false) {
  const errors = [];
  const add = (message) => errors.push(message);
  const counts = { MISSING: 0, IN_PROGRESS: 0, READY: 0, BLOCKED: 0 };
  const levels = Array.isArray(levelConfig?.levels) ? levelConfig.levels : [];
  const expectedCharacters = Array.from({ length: 12 }, (_, index) =>
    `CHR_${String(index + 1).padStart(3, "0")}`
  );
  const expectedLevels = levels.map((level) => level.level_id);
  const expectedMechanisms = [...new Set(
    levels.flatMap((level) => (level.mechanisms ?? []).map((mechanism) => mechanism.mechanism_id))
  )].sort();

  if (manifest?.schema_version !== 1) add("asset manifest schema_version must be 1");
  if (manifest?.gdd_version !== "0.2") add("asset manifest GDD baseline must be 0.2");
  if (manifest?.gdd_chapter_versions?.["18"] !== "0.3") {
    add("asset manifest Chapter 18 baseline must be 0.3");
  }
  if (!Array.isArray(manifest?.entries)) add("entries must be an array");
  if (!sameOrderedValues(manifest?.character_ids, expectedCharacters)) {
    add("manifest must include exactly CHR_001 through CHR_012 in order");
  }
  if (!sameOrderedValues(manifest?.level_ids, expectedLevels)) {
    add("manifest level_ids do not match levels.v1.json");
  }
  if (!Array.isArray(manifest?.mechanism_ids) ||
      [...manifest.mechanism_ids].sort().join("|") !== expectedMechanisms.join("|")) {
    add("manifest mechanism_ids do not match levels.v1.json");
  }

  const expected = new Map();
  const expectedDirectories = new Map();
  for (const characterId of expectedCharacters) {
    for (const [suffix, category] of CHARACTER_CATEGORIES) {
      const id = `${characterId}_${suffix}`;
      addExpected(expected, id, category);
      const folder = suffix === "PORTRAIT" ? "portrait"
        : suffix === "MODEL" ? "model"
        : suffix === "PREVIEW" ? "preview" : "animation";
      expectedDirectories.set(id, `assets/resources/characters/${characterId}/${folder}`);
    }
  }
  for (const [suffix, category] of MAIN_MAP_ASSETS) {
    const id = `MAP_MAIN_001_${suffix}`;
    addExpected(expected, id, category);
    expectedDirectories.set(id, `assets/resources/maps/MAP_MAIN_001/${suffix.toLowerCase()}`);
  }
  for (const levelId of expectedLevels) {
    const id = `${levelId}_GEOMETRY`;
    addExpected(expected, id, "level_geometry");
    expectedDirectories.set(id, `assets/resources/levels/${levelId}`);
  }
  for (const mechanismId of expectedMechanisms) {
    addExpected(expected, mechanismId, "mechanism");
    expectedDirectories.set(mechanismId, `assets/resources/mechanisms/${mechanismId}`);
  }
  for (const id of EFFECT_IDS) {
    addExpected(expected, id, "effect");
    expectedDirectories.set(id, "assets/resources/effects");
  }
  for (const id of UI_IDS) {
    addExpected(expected, id, "ui");
    expectedDirectories.set(id, "assets/resources/ui");
  }
  for (const id of AUDIO_IDS) {
    addExpected(expected, id, "audio");
    expectedDirectories.set(id, "assets/resources/audio");
  }

  const ids = new Set();
  const fileOwners = new Map();
  for (const entry of manifest?.entries ?? []) {
    const id = entry?.asset_id;
    if (!id || ids.has(id)) add(`missing or duplicate asset_id: ${id ?? ""}`);
    ids.add(id);

    const expectedCategory = expected.get(id);
    if (!expectedCategory) add(`unexpected asset_id: ${id}`);
    else if (entry.category !== expectedCategory) {
      add(`${id}: category must be ${expectedCategory}, got ${entry.category}`);
    }

    if (!Object.prototype.hasOwnProperty.call(counts, entry.status)) {
      add(`${id}: invalid status ${entry.status}`);
    } else {
      counts[entry.status] += 1;
    }
    const expectedPriority = P0_ASSET_IDS.has(id) ? "P0"
      : P2_ASSET_IDS.has(id) ? "P2" : "P1";
    if (entry.priority !== expectedPriority) {
      add(`${id}: priority must be ${expectedPriority} per the approved production plan`);
    }
    if (!["P0", "P1", "P2"].includes(entry.priority)) {
      add(`${id}: priority must be P0, P1, or P2`);
    }
    const expectedPhase = entry.priority === "P0" ? "VERTICAL_SLICE"
      : entry.priority === "P1" ? "FIVE_ROOMS_AND_HIDDEN_ENDING"
      : "CONTENT_EXPANSION";
    if (entry.delivery_phase !== expectedPhase) {
      add(`${id}: delivery_phase must be ${expectedPhase} for priority ${entry.priority}`);
    }
    if (entry.required !== true) add(`${id}: MVP manifest entry must be required`);
    if (!entry.expected_directory ||
        !entry.expected_directory.startsWith("assets/resources/") ||
        entry.expected_directory.startsWith("/") ||
        entry.expected_directory.split("/").includes("..")) {
      add(`${id}: expected_directory must be a safe client-relative resources path`);
    }
    const expectedDirectory = expectedDirectories.get(id);
    if (expectedDirectory && entry.expected_directory !== expectedDirectory) {
      add(`${id}: expected_directory must be ${expectedDirectory}, got ${entry.expected_directory}`);
    }
    if (!entry.source_chapter || !entry.acceptance) {
      add(`${id}: source_chapter and acceptance are required`);
    }
    if (!Array.isArray(entry.files)) add(`${id}: files must be an array`);
    if (entry.status === "READY" && (entry.files?.length ?? 0) === 0) {
      add(`${id}: READY requires at least one delivered file`);
    }
    if (entry.status === "READY") {
      const provenance = entry.provenance;
      const allowedSourceTypes = new Set([
        "ORIGINAL_INTERNAL",
        "COMMISSIONED",
        "LICENSED",
        "PUBLIC_DOMAIN",
        "GENERATED_WITH_REVIEW"
      ]);
      if (!provenance || !allowedSourceTypes.has(provenance.source_type)) {
        add(`${id}: READY requires provenance.source_type from the approved source types`);
      }
      for (const field of ["source_reference", "license", "license_evidence", "acceptance_evidence"]) {
        if (typeof provenance?.[field] !== "string" || provenance[field].trim().length === 0) {
          add(`${id}: READY requires non-empty provenance.${field}`);
        }
      }
      for (const field of ["license_evidence", "acceptance_evidence"]) {
        if (!isSafeEvidencePath(provenance?.[field])) {
          add(`${id}: provenance.${field} must be a safe Markdown path under docs/engineering/assets/evidence/`);
        }
      }
    }
    for (const file of entry.files ?? []) {
      if (typeof file !== "string" || file.startsWith("/") ||
          file.split("/").includes("..") ||
          !file.startsWith(`${entry.expected_directory}/`)) {
        add(`${id}: file must be a safe path inside expected_directory: ${file}`);
        continue;
      }
      const owner = fileOwners.get(file);
      if (owner) add(`${id}: file path is already assigned to ${owner}: ${file}`);
      else fileOwners.set(file, id);
    }
    if (strict && entry.required && entry.status !== "READY") {
      add(`${id}: release blocker status=${entry.status}`);
    }
  }

  for (const id of expected.keys()) {
    if (!ids.has(id)) add(`required asset missing from manifest: ${id}`);
  }
  for (const id of ids) {
    if (!expected.has(id)) add(`orphan asset in manifest: ${id}`);
  }
  const total = manifest?.entries?.length ?? 0;
  if (total !== expected.size) add(`manifest must contain exactly ${expected.size} entries, found ${total}`);
  if (counts.READY === total && total > 0 && manifest.status !== "READY") {
    add("manifest status must be READY when every entry is READY");
  }
  if (counts.READY !== total && manifest.status === "READY") {
    add("manifest cannot be READY while required entries are not all READY");
  }

  return { errors, counts, total, expectedCount: expected.size };
}
