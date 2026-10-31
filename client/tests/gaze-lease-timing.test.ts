import { describe, expect, it } from "vitest";
import { getGazeLeaseRenewalInterval } from "../assets/scripts/world/gaze-lease-timing";

describe("getGazeLeaseRenewalInterval", () => {
  it.each([
    [5000, 1666],
    [3000, 1000],
    [750, 250],
    [900, 300]
  ])("renews lease %s ms at interval %s ms", (lease, expected) => {
    expect(getGazeLeaseRenewalInterval(lease)).toBe(expected);
  });

  it.each([null, undefined, 0, -1, 749, Number.NaN, Number.POSITIVE_INFINITY])(
    "rejects invalid lease timeout %s",
    (lease) => {
      expect(getGazeLeaseRenewalInterval(lease)).toBeUndefined();
    }
  );
});
