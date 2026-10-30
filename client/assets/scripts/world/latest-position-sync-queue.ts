export interface PositionSample {
  x: number;
  y: number;
}

export class LatestPositionSyncQueue {
  private pending?: PositionSample;
  private inFlight?: Promise<void>;

  constructor(
    private readonly send: (position: PositionSample) => Promise<unknown>,
    private readonly onError: (error: unknown) => void
  ) {}

  enqueue(position: PositionSample): void {
    this.pending = { ...position };
    this.startDrain(false);
  }

  /** Wait for an in-flight background request without requiring it to succeed. */
  async waitForIdle(): Promise<void> {
    while (this.inFlight) await this.inFlight;
  }

  /**
   * Wait for in-flight samples, then ensure the newest requested position has
   * been accepted by the server. Unlike background updates, flush propagates
   * send failures so interactions can be blocked rather than use stale coords.
   */
  async flush(position: PositionSample): Promise<void> {
    this.pending = { ...position };
    while (this.pending || this.inFlight) {
      const task = this.startDrain(true);
      if (task) await task;
    }
  }

  private startDrain(propagateErrors: boolean): Promise<void> | undefined {
    if (this.inFlight) return this.inFlight;
    if (!this.pending) return undefined;

    let failed = false;
    const task = (async () => {
      while (this.pending) {
        const next = this.pending;
        this.pending = undefined;
        try {
          await this.send({ ...next });
        } catch (error) {
          failed = true;
          if (!this.pending) this.pending = next;
          if (propagateErrors) throw error;
          try {
            this.onError(error);
          } catch {
            // Error reporting must not break the queue's lifecycle.
          }
          break;
        }
      }
    })();

    this.inFlight = task;
    const finish = () => {
      if (this.inFlight === task) this.inFlight = undefined;
      if (this.pending && !failed && !propagateErrors) {
        this.startDrain(false);
      }
    };
    void task.then(finish, finish);
    return task;
  }
}
