export interface PrototypeLayoutConfig {
  bounds: {
    minX: number;
    maxX: number;
    minY: number;
    maxY: number;
  };
  spawn: { x: number; y: number };
  movementSpeed: number;
  interactionRadius: number;
  positionSyncIntervalMs: number;
}

/** Parse the server-owned prototype layout and control tuning for a level. */
export function parsePrototypeLayoutConfig(
  config: Record<string, unknown>
): PrototypeLayoutConfig {
  const bounds = config.prototype_bounds;
  const spawn = config.prototype_spawn;
  const controls = config.prototype_controls;

  if (
    !bounds || typeof bounds !== "object" || Array.isArray(bounds) ||
    !spawn || typeof spawn !== "object" || Array.isArray(spawn) ||
    !controls || typeof controls !== "object" || Array.isArray(controls)
  ) {
    throw new Error("Level prototype layout configuration is incomplete");
  }

  const b = bounds as Record<string, unknown>;
  const p = spawn as Record<string, unknown>;
  const c = controls as Record<string, unknown>;
  const minX = b.min_x;
  const maxX = b.max_x;
  const minY = b.min_y;
  const maxY = b.max_y;
  const x = p.x;
  const y = p.y;
  const movementSpeed = c.movement_speed;
  const interactionRadius = c.interaction_radius;
  const positionSyncIntervalMs = c.position_sync_interval_ms;

  if (
    ![minX, maxX, minY, maxY, x, y, movementSpeed, interactionRadius, positionSyncIntervalMs]
      .every((value) => typeof value === "number" && Number.isFinite(value)) ||
    (minX as number) >= (maxX as number) ||
    (minY as number) >= (maxY as number) ||
    (x as number) < (minX as number) ||
    (x as number) > (maxX as number) ||
    (y as number) < (minY as number) ||
    (y as number) > (maxY as number) ||
    (movementSpeed as number) <= 0 ||
    (interactionRadius as number) <= 0 ||
    !Number.isInteger(positionSyncIntervalMs) ||
    (positionSyncIntervalMs as number) < 50 ||
    (positionSyncIntervalMs as number) > 1000
  ) {
    throw new Error("Level prototype layout configuration contains invalid values");
  }

  return {
    bounds: {
      minX: minX as number,
      maxX: maxX as number,
      minY: minY as number,
      maxY: maxY as number
    },
    spawn: { x: x as number, y: y as number },
    movementSpeed: movementSpeed as number,
    interactionRadius: interactionRadius as number,
    positionSyncIntervalMs: positionSyncIntervalMs as number
  };
}
