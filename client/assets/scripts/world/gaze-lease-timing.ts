export function getGazeLeaseRenewalInterval(
  leaseTimeoutMs: number | null | undefined
): number | undefined {
  if (leaseTimeoutMs === null || leaseTimeoutMs === undefined ||
      !Number.isFinite(leaseTimeoutMs) || leaseTimeoutMs < 750) {
    return undefined;
  }
  return Math.max(250, Math.floor(leaseTimeoutMs / 3));
}
