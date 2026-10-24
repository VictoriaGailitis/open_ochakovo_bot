// Revisions are assigned when a save is scheduled, before any network queue.
// A late older request can therefore never replace the last edited draft.
let clock = 0;
export function syncDraftClock(revisions: number[]) {
  clock = Math.max(clock, ...revisions.filter(Number.isSafeInteger));
}
export function nextDraftRevision() {
  clock = Math.max(Date.now(), clock + 1);
  return clock;
}
