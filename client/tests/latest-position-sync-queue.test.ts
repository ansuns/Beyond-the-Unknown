import { describe, expect, it, vi } from "vitest";
import { LatestPositionSyncQueue } from "../assets/scripts/world/latest-position-sync-queue";

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("LatestPositionSyncQueue", () => {
  it("sends the newest queued sample after an in-flight request", async () => {
    const first = deferred<void>();
    const send = vi.fn()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValue(undefined);
    const queue = new LatestPositionSyncQueue(send, vi.fn());

    queue.enqueue({ x: 1, y: 1 });
    queue.enqueue({ x: 2, y: 2 });
    queue.enqueue({ x: 3, y: 3 });
    first.resolve();

    await vi.waitFor(() => expect(send).toHaveBeenCalledTimes(2));
    expect(send.mock.calls.map(([point]) => point)).toEqual([
      { x: 1, y: 1 },
      { x: 3, y: 3 }
    ]);
  });

  it("flushes the final position after all background samples", async () => {
    const first = deferred<void>();
    const send = vi.fn()
      .mockImplementationOnce(() => first.promise)
      .mockResolvedValue(undefined);
    const queue = new LatestPositionSyncQueue(send, vi.fn());

    queue.enqueue({ x: 1, y: 1 });
    const flush = queue.flush({ x: 9, y: 4 });
    first.resolve();
    await flush;

    expect(send.mock.calls.map(([point]) => point)).toEqual([
      { x: 1, y: 1 },
      { x: 9, y: 4 }
    ]);
  });

  it("reports background failures and retries the latest position on flush", async () => {
    const onError = vi.fn();
    const send = vi.fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue(undefined);
    const queue = new LatestPositionSyncQueue(send, onError);

    queue.enqueue({ x: 2, y: 3 });
    await vi.waitFor(() => expect(onError).toHaveBeenCalledOnce());
    await queue.flush({ x: 7, y: 6 });

    expect(send.mock.calls.map(([point]) => point)).toEqual([
      { x: 2, y: 3 },
      { x: 7, y: 6 }
    ]);
  });

  it("propagates an explicit flush failure", async () => {
    const queue = new LatestPositionSyncQueue(
      vi.fn().mockRejectedValue(new Error("server unavailable")),
      vi.fn()
    );
    await expect(queue.flush({ x: 4, y: 4 })).rejects.toThrow("server unavailable");
  });
});
