export type PrototypeMechanismShape =
  | "BRIDGE"
  | "DOOR"
  | "ENERGY"
  | "GATE"
  | "HIDEABLE"
  | "PLATFORM"
  | "CORE"
  | "GENERIC";

export type PrototypeMechanismVisualState = "ACTIVE" | "LOCKED" | "IDLE";

const SHAPES: Record<string, PrototypeMechanismShape> = {
  PLATFORM_BRIDGE: "BRIDGE",
  DOOR_BARRIER: "DOOR",
  ENERGY_NODE: "ENERGY",
  EXIT_GATE: "GATE",
  HIDDEN_GATE: "GATE",
  HIDEABLE: "HIDEABLE",
  LIGHT_REVEAL: "ENERGY",
  MOVING_OBJECT: "PLATFORM",
  ENDING_CORE: "CORE"
};

const ACTIVE_STATES = new Set([
  "ACTIVE", "TRIGGERED", "OPEN", "REVEALED", "REVERSED",
  "ENDPOINT_LOCKED", "ENDING_REVEALED"
]);
const LOCKED_STATES = new Set([
  "LOCKED", "SEALED", "CLOSED", "DORMANT", "INVISIBLE", "HIDDEN", "INACTIVE"
]);

export function getPrototypeMechanismShape(mechanismType: string): PrototypeMechanismShape {
  return SHAPES[mechanismType] ?? "GENERIC";
}

export function getPrototypeMechanismVisualState(
  status: string | undefined,
  visible: boolean | undefined
): PrototypeMechanismVisualState {
  if (visible === true || (status !== undefined && ACTIVE_STATES.has(status))) return "ACTIVE";
  if (status !== undefined && LOCKED_STATES.has(status)) return "LOCKED";
  return "IDLE";
}
