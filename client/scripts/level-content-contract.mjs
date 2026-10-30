export function validateLevelContentConfig(config) {
  const errors = [];
  const add = (message) => errors.push(message);
  const levels = Array.isArray(config?.levels) ? config.levels : [];
  const levelById = new Map(levels.map((level) => [level.level_id, level]));

  if (config?.schema_version !== 1) add("schema_version must be 1");
  if (levels.length !== 6) add(`expected 5 normal rooms + 1 hidden room, found ${levels.length}`);
  if (levelById.size !== levels.length) add("duplicate level_id");

  const rooms = levels.filter((level) => !level.is_hidden);
  const hidden = levels.filter((level) => level.is_hidden);
  const roomIndexes = rooms.map((level) => level.room_index).sort((a, b) => a - b);
  if (rooms.length !== 5 || roomIndexes.join(",") !== "1,2,3,4,5") {
    add("normal rooms must have unique room_index values 1..5");
  }
  if (hidden.length !== 1 || hidden[0]?.level_id !== "LV-HIDDEN-01" ||
      hidden[0]?.room_index !== null || hidden[0]?.is_enabled !== true) {
    add("expected exactly enabled LV-HIDDEN-01 as the hidden room with room_index=null");
  }

  const entranceIds = new Set();
  const mechanismIds = new Set();
  const objectiveIds = new Set();
  for (const level of levels) {
    if (!level.entrance_id || entranceIds.has(level.entrance_id)) {
      add(`${level.level_id}: missing or duplicate entrance_id ${level.entrance_id ?? ""}`);
    }
    entranceIds.add(level.entrance_id);

    const mechanisms = Array.isArray(level.mechanisms) ? level.mechanisms : [];
    const localMechanisms = new Set();
    for (const mechanism of mechanisms) {
      const id = mechanism.mechanism_id;
      if (!id || localMechanisms.has(id) || mechanismIds.has(id)) {
        add(`${level.level_id}: missing or duplicate mechanism_id ${id ?? ""}`);
      }
      localMechanisms.add(id);
      mechanismIds.add(id);
    }

    const layout = level.prototype_layout;
    if (!layout?.prototype_only || layout.status !== "PROTOTYPE_TUNING_PENDING") {
      add(`${level.level_id}: prototype_layout must remain explicitly provisional`);
    }
    const bounds = layout?.bounds;
    const spawn = layout?.spawn;
    if (!bounds || !spawn ||
        !Number.isFinite(spawn.x) || !Number.isFinite(spawn.y) ||
        spawn.x < bounds.min_x || spawn.x > bounds.max_x ||
        spawn.y < bounds.min_y || spawn.y > bounds.max_y) {
      add(`${level.level_id}: prototype spawn must be inside configured bounds`);
    }

    for (const mechanism of mechanisms) {
      const position = mechanism.position;
      if (!mechanism.prototype_only || !position || !bounds ||
          !Number.isFinite(position.x) || !Number.isFinite(position.y) ||
          position.x < bounds.min_x || position.x > bounds.max_x ||
          position.y < bounds.min_y || position.y > bounds.max_y) {
        add(`${level.level_id}: mechanism ${mechanism.mechanism_id} requires a valid provisional position`);
      }
      if (mechanism.config?.prototype_only !== true) {
        add(`${level.level_id}: mechanism ${mechanism.mechanism_id} config must be marked prototype_only`);
      }
      const linkedMechanismId = mechanism.config?.linked_mechanism_id;
      if (linkedMechanismId && !localMechanisms.has(linkedMechanismId)) {
        add(`${level.level_id}: mechanism ${mechanism.mechanism_id} links to missing mechanism ${linkedMechanismId}`);
      }
    }

    const objectives = Array.isArray(level.necessary_objectives) ? level.necessary_objectives : [];
    if (objectives.length === 0) add(`${level.level_id}: necessary_objectives must not be empty`);
    for (const objective of objectives) {
      if (!objective.objective_id || objectiveIds.has(objective.objective_id)) {
        add(`${level.level_id}: missing or duplicate objective_id ${objective.objective_id ?? ""}`);
      }
      objectiveIds.add(objective.objective_id);
      if (!localMechanisms.has(objective.mechanism_id)) {
        add(`${level.level_id}: objective ${objective.objective_id} references missing mechanism ${objective.mechanism_id}`);
      }
      if (objective.required_combo &&
          !(level.required_combos ?? []).includes(objective.required_combo)) {
        add(`${level.level_id}: objective ${objective.objective_id} references undeclared combo ${objective.required_combo}`);
      }
    }
    const requiredCombos = level.required_combos ?? [];
    if (new Set(requiredCombos).size !== requiredCombos.length) {
      add(`${level.level_id}: duplicate required_combos`);
    }

    const prototypeCombos = Array.isArray(level.prototype_combos) ? level.prototype_combos : [];
    if (!Array.isArray(level.prototype_combos)) {
      add(`${level.level_id}: prototype_combos must be an array`);
    }
    const prototypeComboIds = prototypeCombos.map((combo) => combo.combo_id);
    if (!level.is_hidden && (level.room_index ?? 0) > 1 &&
        [...prototypeComboIds].sort().join("|") !== [...requiredCombos].sort().join("|")) {
      add(`${level.level_id}: every required combo must have exactly one prototype control definition`);
    }
    if (new Set(prototypeComboIds).size !== prototypeComboIds.length) {
      add(`${level.level_id}: duplicate prototype combo_id`);
    }
    for (const combo of prototypeCombos) {
      if (!requiredCombos.includes(combo.combo_id)) {
        add(`${level.level_id}: prototype combo ${combo.combo_id} is not listed in required_combos`);
      }
      if (!localMechanisms.has(combo.target_mechanism_id)) {
        add(`${level.level_id}: prototype combo ${combo.combo_id} references missing target ${combo.target_mechanism_id}`);
      }
      if (!Array.isArray(combo.rule_sequence) || combo.rule_sequence.length !== 2 ||
          combo.rule_sequence.some((rule) => !["RULE_ECHO", "RULE_GAZE", "RULE_REVERSE"].includes(rule))) {
        add(`${level.level_id}: prototype combo ${combo.combo_id} must define exactly two known law rules`);
      }
      if (typeof combo.display_name !== "string" || !combo.display_name.trim()) {
        add(`${level.level_id}: prototype combo ${combo.combo_id} requires a display_name`);
      }
      if (typeof combo.maintain_gaze !== "boolean") {
        add(`${level.level_id}: prototype combo ${combo.combo_id} requires a maintain_gaze boolean`);
      }
    }
  }

  const routes = Array.isArray(config?.hidden_routes) ? config.hidden_routes : [];
  const routeIds = new Set();
  for (const route of routes) {
    if (!route.hidden_route_id || routeIds.has(route.hidden_route_id)) {
      add(`duplicate or missing hidden route ${route.hidden_route_id ?? ""}`);
    }
    routeIds.add(route.hidden_route_id);
    if (route.is_enabled !== true) add(`${route.hidden_route_id}: MVP hidden route must be enabled`);

    const target = levelById.get(route.result);
    if (!target?.is_hidden || target.is_enabled !== true) {
      add(`${route.hidden_route_id}: result must reference an enabled hidden level`);
    }
    const prerequisites = route.prerequisite_levels ?? [];
    for (const id of prerequisites) {
      if (!levelById.has(id) || levelById.get(id).is_hidden) {
        add(`${route.hidden_route_id}: invalid prerequisite level ${id}`);
      }
    }
    const finalRoom = levelById.get("LV-ROOM-05");
    const finalMechanisms = new Set((finalRoom?.mechanisms ?? []).map((item) => item.mechanism_id));
    const triggerMechanisms = route.trigger_mechanisms ?? [];
    const triggerCombos = route.trigger_combo ?? [];
    if (triggerMechanisms.length === 0 || triggerMechanisms.length !== triggerCombos.length) {
      add(`${route.hidden_route_id}: trigger combo and mechanism sequences must have equal non-zero lengths`);
    }
    if (new Set(triggerMechanisms).size !== triggerMechanisms.length ||
        new Set(triggerCombos).size !== triggerCombos.length) {
      add(`${route.hidden_route_id}: trigger sequences must not contain duplicates`);
    }
    for (const id of triggerMechanisms) {
      if (!finalMechanisms.has(id)) add(`${route.hidden_route_id}: trigger mechanism ${id} is missing from LV-ROOM-05`);
    }
    for (const combo of triggerCombos) {
      if (!(finalRoom?.required_combos ?? []).includes(combo)) {
        add(`${route.hidden_route_id}: combo ${combo} is not required by LV-ROOM-05`);
      }
    }

    const objectivesByCombo = new Map(
      (finalRoom?.necessary_objectives ?? [])
        .filter((objective) => objective.required_combo)
        .map((objective) => [objective.required_combo, objective.mechanism_id])
    );
    for (let index = 0; index < Math.min(triggerCombos.length, triggerMechanisms.length); index += 1) {
      if (objectivesByCombo.get(triggerCombos[index]) !== triggerMechanisms[index]) {
        add(`${route.hidden_route_id}: sequence pair ${triggerCombos[index]} -> ${triggerMechanisms[index]} does not match ROOM-05 objective mapping`);
      }
    }

    if (target?.unlock?.hidden_route_id !== route.hidden_route_id) {
      add(`${route.hidden_route_id}: target unlock.hidden_route_id does not point back to route`);
    }
    const required = target?.unlock?.requires_completed_levels ?? [];
    if ([...prerequisites].sort().join("|") !== [...required].sort().join("|")) {
      add(`${route.hidden_route_id}: route prerequisites and hidden-level unlock prerequisites differ`);
    }
  }
  if (!routeIds.has("HIDDEN-ROUTE-01") || routes.length !== 1) {
    add("MVP requires exactly one HIDDEN-ROUTE-01 route");
  }

  return errors;
}
