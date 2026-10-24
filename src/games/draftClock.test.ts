import { test } from "node:test";
import assert from "node:assert/strict";
import { DraftSnapshotClock } from "../draftClock";

test("an unchanged tab flush keeps its saved revision and cannot replace a later remote edit", (t) => {
  let now = 1000;
  t.mock.method(Date, "now", () => now);
  const oldSnapshot = { note: "Первый черновик" };
  const tabA = new DraftSnapshotClock(oldSnapshot, 100);
  const initialB = { ...oldSnapshot };
  const tabB = new DraftSnapshotClock(initialB, 100);
  const newerRemote = { note: "Новая правка другой вкладки" };
  const remoteRevision = tabB.edit(newerRemote);
  let stored = { draft: newerRemote, revision: remoteRevision };
  now = 50000;
  // The same snapshot is retried by debounce, unmount and pagehide much later.
  for (const flush of ["debounce", "unmount", "pagehide"]) {
    const revision = tabA.revisionOf(oldSnapshot);
    if (revision >= stored.revision) stored = { draft: oldSnapshot, revision };
    assert.equal(revision, 100, flush);
    assert.equal(stored.draft, newerRemote, flush);
    assert.equal(stored.revision, remoteRevision, flush);
  }
  assert.equal(
    tabA.edit({ ...oldSnapshot }),
    100,
    "a no-op edit must not make an old snapshot newer",
  );
});

test("real edits receive one revision and queued older snapshots keep their original revision", () => {
  const first = { note: "Начало" };
  const clock = new DraftSnapshotClock(first, 0);
  const second = { note: "Вторая запись" };
  const secondRevision = clock.edit(second);
  assert.ok(secondRevision > 0);
  assert.equal(clock.revisionOf(second), secondRevision);
  const third = { note: "Третья запись" };
  const thirdRevision = clock.edit(third);
  assert.ok(thirdRevision > secondRevision);
  assert.equal(clock.revisionOf(second), secondRevision);
  assert.equal(clock.revisionOf(first), 0);
  assert.equal(clock.revisionOf(third), thirdRevision);
  assert.equal(clock.edit({ ...third }), thirdRevision);
});

test("conflict restoration adopts the server revision without minting a newer unchanged flush", () => {
  const local = { note: "Старое" };
  const clock = new DraftSnapshotClock(local, 17);
  const server = { note: "С сервера" };
  const serverRevision = Date.now() + 100000;
  clock.restore(server, serverRevision);
  assert.equal(clock.revisionOf(server), serverRevision);
  assert.equal(clock.edit({ ...server }), serverRevision);
  const edited = { note: "Моя новая правка после восстановления" };
  assert.ok(clock.edit(edited) > serverRevision);
  assert.equal(clock.revisionOf(server), serverRevision);
});

test("flush cannot silently assign a revision to an unregistered snapshot", () => {
  const clock = new DraftSnapshotClock({ note: "Начало" }, 5);
  assert.throws(
    () => clock.revisionOf({ note: "Не зарегистрирован" }),
    /не зарегистрирован/,
  );
});
