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

export interface PrototypePoint {
  x: number;
  y: number;
}

export interface PrototypeRoomSize {
  width: number;
  height: number;
}

export function getPrototypeRoomDimensions(
  bounds: PrototypeLayoutConfig["bounds"],
  scale: number
): PrototypeRoomSize {
  if (!Number.isFinite(scale) || scale <= 0) {
    throw new Error("Prototype room scale must be a positive finite number");
  }
  return {
    width: (bounds.maxX - bounds.minX) * scale,
    height: (bounds.maxY - bounds.minY) * scale
  };
}

export function prototypeLevelToLocal(
  point: PrototypePoint,
  bounds: PrototypeLayoutConfig["bounds"],
  scale: number
): PrototypePoint {
  const room = getPrototypeRoomDimensions(bounds, scale);
  return {
    x: -room.width / 2 + (point.x - bounds.minX) * scale,
    y: -room.height / 2 + (point.y - bounds.minY) * scale
  };
}

export function prototypeLocalToLevel(
  point: PrototypePoint,
  bounds: PrototypeLayoutConfig["bounds"],
  scale: number
): PrototypePoint {
  const room = getPrototypeRoomDimensions(bounds, scale);
  return {
    x: Math.max(bounds.minX, Math.min(bounds.maxX, (point.x + room.width / 2) / scale + bounds.minX)),
    y: Math.max(bounds.minY, Math.min(bounds.maxY, (point.y + room.height / 2) / scale + bounds.minY))
  };
}

export function calculatePrototypeRoomScale(
  bounds: PrototypeLayoutConfig["bounds"],
  size: { width: number; height: number }
): number {
  const spanX = bounds.maxX - bounds.minX;
  const spanY = bounds.maxY - bounds.minY;
  if (
    !Number.isFinite(spanX) || !Number.isFinite(spanY) ||
    spanX <= 0 || spanY <= 0 ||
    !Number.isFinite(size.width) || !Number.isFinite(size.height) ||
    size.width <= 0 || size.height <= 0
  ) {
    throw new Error("Prototype room bounds and viewport size must be positive and finite");
  }
  const availableWidth = Math.max(160, size.width - 64);
  const availableHeight = Math.max(120, size.height - 240);
  return Math.min(40, availableWidth / spanX, availableHeight / spanY);
}
