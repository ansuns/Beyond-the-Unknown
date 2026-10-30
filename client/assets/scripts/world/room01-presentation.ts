export interface Room01VisualState {
  hiddenTargetVisible: boolean;
  exitOpen: boolean;
}

export function deriveRoom01VisualState(
  mechanismStates: ReadonlyMap<string, Record<string, unknown>>
): Room01VisualState {
  return {
    hiddenTargetVisible:
      mechanismStates.get("M01-HIDEABLE-01")?.visible === true,
    exitOpen:
      mechanismStates.get("M01-EXIT-01")?.status === "TRIGGERED"
  };
}
