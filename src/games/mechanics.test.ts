import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  appendRoute,
  footprint,
  gearDirections,
  placementError,
  runSignal,
} from "./mechanics";
import type {
  Batch,
  DeliveryPuzzle,
  MovementPuzzle,
  SignalPuzzle,
  Task,
} from "./types";
const catalog = JSON.parse(
  readFileSync(new URL("../../server/catalog.json", import.meta.url), "utf8"),
) as { tasks: Task[] };
test("first matching signal rule wins, default catches remaining cases", () => {
  const p = catalog.tasks.find((t) => t.id === "signal-1")!
    .puzzle as SignalPuzzle;
  assert.ok(
    runSignal(p, [
      { condition: "red", output: "left" },
      { condition: "always", output: "right" },
    ]).every((row) => row.correct),
  );
  const conflicting = runSignal(p, [
    { condition: "always", output: "right" },
    { condition: "red", output: "left" },
  ]);
  assert.equal(conflicting[0].ruleIndex, 0);
  assert.equal(conflicting[0].correct, false);
  assert.equal(
    runSignal(p, [{ condition: "red", output: "left" }])[1].output,
    undefined,
  );
});
test("all three signal variants execute their distinct condition", () => {
  for (const task of catalog.tasks.filter((t) => t.game === "signal")) {
    const p = task.puzzle as SignalPuzzle;
    const condition =
      p.rule === "color" ? "red" : p.rule === "mark" ? "marked" : "red_marked";
    assert.ok(
      runSignal(p, [
        { condition, output: "left" },
        { condition: "always", output: "right" },
      ]).every((row) => row.correct),
      task.id,
    );
  }
});
test("gear chain flips rotation and cannot jump over gaps", () => {
  const p = catalog.tasks.find((t) => t.id === "movement-1")!
    .puzzle as MovementPuzzle;
  const chain = [
    { x: 1, y: 1 },
    { x: 2, y: 1 },
    { x: 3, y: 1 },
  ];
  const directions = gearDirections(p, chain);
  assert.equal(directions.get("1,1"), -1);
  assert.equal(directions.get("4,1"), 1);
  assert.equal(gearDirections(p, [chain[0], chain[2]]).get("4,1"), undefined);
});
test("packing supports rotation and rejects reservation, collision and bounds", () => {
  const p = catalog.tasks.find((t) => t.id === "delivery-1")!
    .puzzle as DeliveryPuzzle;
  const batch = p.batches[0];
  const origin = { batchId: batch.id, x: 0, y: 0, rotated: false };
  assert.deepEqual(footprint(batch, { ...origin, rotated: true }), [
    { x: 0, y: 0 },
    { x: 0, y: 1 },
  ]);
  assert.equal(
    placementError(batch, origin, [], p.batches, p.width, p.height),
    null,
  );
  assert.match(
    placementError(
      batch,
      { ...origin, x: p.width - 1 },
      [],
      p.batches,
      p.width,
      p.height,
    )!,
    /край/,
  );
  assert.match(
    placementError(
      p.batches[2],
      { ...origin, batchId: p.batches[2].id },
      [],
      p.batches,
      p.width,
      p.height,
    )!,
    /зарезервирована/,
  );
  const one: Batch = {
    id: "one",
    product: "water",
    reserved: false,
    cells: [[0, 0]],
    location: { x: 0, y: 0 },
  };
  assert.match(
    placementError(
      one,
      { ...origin, batchId: "one" },
      [origin],
      [...p.batches, one],
      p.width,
      p.height,
    )!,
    /уже стоит/,
  );
});
test("warehouse route advances by one orthogonal cell and permits retracing", () => {
  const path = [{ x: 0, y: 0 }];
  assert.equal(appendRoute(path, { x: 1, y: 1 }), null);
  assert.equal(appendRoute(path, { x: 0, y: 0 }), null);
  const next = appendRoute(path, { x: 1, y: 0 })!;
  assert.deepEqual(next, [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
  ]);
  assert.equal(path.length, 1);
  assert.equal(appendRoute(next, { x: 0, y: 0 })?.length, 3);
});
