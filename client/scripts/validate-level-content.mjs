import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

const configPath = resolve(process.cwd(), "../docs/engineering/levels/levels.v1.json");
const config = JSON.parse(await readFile(configPath, "utf8"));
const errors = [];
const add = (message) => errors.push(message);
const levels = config.levels ?? [];
const levelById = new Map(levels.map((level) => [level.level_id, level]));

if (config.schema_version !== 1) add("schema_version must be 1");
if (levels.length !== 6) add(`expected 5 normal rooms + 1 hidden room, found ${levels.length}`);
if (new Set(levels.map((level) => level.level_id)).size !== levels.length) add("duplicate level_id");

const rooms = levels.filter((level) => !level.is_hidden);
const hidden = levels.filter((level) => level.is_hidden);
if (rooms.length !== 5 || rooms.map((level) => level.room_index).sort().join(",") !== "1,2,3,4,5") {
  add("normal rooms must have unique room_index values 1..5");
}
if (hidden.length !== 1 || hidden[0]?.level_id !== "LV-HIDDEN-01" || hidden[0]?.room_index !== null) {
  add("expected exactly LV-HIDDEN-01 as the hidden room with room_index=null");
}

for (const level of levels) {
  const mechanisms = level.mechanisms ?? [];
  const mechanismIds = mechanisms.map((item) => item.mechanism_id);
  if (new Set(mechanismIds).size !== mechanismIds.length) add(`${level.level_id}: duplicate mechanism_id`);
  const layout = level.prototype_layout;
  if (!layout?.prototype_only || layout.status !== "PROTOTYPE_TUNING_PENDING") {
    add(`${level.level_id}: prototype_layout must remain explicitly provisional`);
  }
  const bounds = layout?.bounds;
  const spawn = layout?.spawn;
  if (!bounds || !spawn ||
      spawn.x < bounds.min_x || spawn.x > bounds.max_x ||
      spawn.y < bounds.min_y || spawn.y > bounds.max_y) {
    add(`${level.level_id}: prototype spawn must be inside configured bounds`);
  }
  for (const mechanism of mechanisms) {
    const position = mechanism.position;
    if (!mechanism.prototype_only || !position ||
        !Number.isFinite(position.x) || !Number.isFinite(position.y) ||
        position.x < bounds.min_x || position.x > bounds.max_x ||
        position.y < bounds.min_y || position.y > bounds.max_y) {
      add(`${level.level_id}: mechanism ${mechanism.mechanism_id} requires a valid provisional position`);
    }
    if (mechanism.config?.prototype_only !== true) {
      add(`${level.level_id}: mechanism ${mechanism.mechanism_id} config must be marked prototype_only`);
    }
  }
  for (const objective of level.necessary_objectives ?? []) {
    if (!mechanismIds.includes(objective.mechanism_id)) {
      add(`${level.level_id}: objective ${objective.objective_id} references missing mechanism ${objective.mechanism_id}`);
    }
  }
}

const routeIds = new Set();
for (const route of config.hidden_routes ?? []) {
  if (routeIds.has(route.hidden_route_id)) add(`duplicate hidden route ${route.hidden_route_id}`);
  routeIds.add(route.hidden_route_id);
  const target = levelById.get(route.result);
  if (!target?.is_hidden) add(`${route.hidden_route_id}: result must reference an existing hidden level`);
  for (const id of route.prerequisite_levels ?? []) {
    if (!levelById.has(id) || levelById.get(id).is_hidden) add(`${route.hidden_route_id}: invalid prerequisite level ${id}`);
  }
  const finalRoom = levelById.get("LV-ROOM-05");
  const finalMechanisms = new Set((finalRoom?.mechanisms ?? []).map((item) => item.mechanism_id));
  for (const id of route.trigger_mechanisms ?? []) {
    if (!finalMechanisms.has(id)) add(`${route.hidden_route_id}: trigger mechanism ${id} is missing from LV-ROOM-05`);
  }
  for (const combo of route.trigger_combo ?? []) {
    if (!(finalRoom?.required_combos ?? []).includes(combo)) add(`${route.hidden_route_id}: combo ${combo} is not required by LV-ROOM-05`);
  }
  if (target?.unlock?.hidden_route_id !== route.hidden_route_id) {
    add(`${route.hidden_route_id}: target unlock.hidden_route_id does not point back to route`);
  }
  const required = target?.unlock?.requires_completed_levels ?? [];
  if ([...(route.prerequisite_levels ?? [])].sort().join("|") !== [...required].sort().join("|")) {
    add(`${route.hidden_route_id}: route prerequisites and hidden-level unlock prerequisites differ`);
  }
}

if (errors.length) {
  console.error("Level content validation failed:");
  for (const error of errors) console.error(`- ${error}`);
  process.exit(1);
}
console.log("Level content valid: five normal rooms, one hidden room, unique mechanisms/objectives and consistent hidden-route references.");
