// The global clock advances for edits. Flushes reuse the revision attached to
// their snapshot so an unchanged old tab cannot overwrite another tab’s edits.
let clock = 0;
export class DraftConflictError extends Error {
  constructor(
    public draft: unknown,
    public revision: number,
  ) {
    super(
      "Сервер отклонил устаревшее сохранение: черновик изменён в другой вкладке.",
    );
    this.name = "DraftConflictError";
  }
}
export function syncDraftClock(revisions: number[]) {
  clock = Math.max(clock, ...revisions.filter(Number.isSafeInteger));
}
export function nextDraftRevision() {
  clock = Math.max(Date.now(), clock + 1);
  return clock;
}

/** Revisions belong to edited snapshots, never to a later retry or flush. */
export class DraftSnapshotClock<T extends object> {
  private revisions = new WeakMap<T, number>();
  private currentRevision = 0;
  private serialized = "";

  constructor(initial: T, revision = 0) {
    this.restore(initial, revision);
  }

  edit(snapshot: T): number {
    const serialized = JSON.stringify(snapshot);
    const revision =
      serialized === this.serialized
        ? this.currentRevision
        : nextDraftRevision();
    this.currentRevision = revision;
    this.serialized = serialized;
    this.revisions.set(snapshot, revision);
    return revision;
  }

  restore(snapshot: T, revision: number): void {
    const validRevision =
      Number.isSafeInteger(revision) && revision >= 0 ? revision : 0;
    syncDraftClock([validRevision]);
    this.currentRevision = validRevision;
    this.serialized = JSON.stringify(snapshot);
    this.revisions.set(snapshot, validRevision);
  }

  revisionOf(snapshot: T): number {
    const revision = this.revisions.get(snapshot);
    if (revision === undefined)
      throw new Error("Черновик не зарегистрирован как изменённый снимок.");
    return revision;
  }
}
