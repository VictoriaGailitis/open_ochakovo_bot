import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  appendRoute,
  footprint,
  gearDirections,
  movementNetwork,
  placementError,
  runSignal,
} from "./mechanics";
import type {
  Batch,
  Belt,
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

const shaft = (x: number, y = 1) => ({ x, y });
const belt = (from: number, to: number): Belt => ({
  from: shaft(from),
  to: shaft(to),
});
function beltPuzzle(): MovementPuzzle {
  return {
    width: 5,
    height: 3,
    source: { ...shaft(0), direction: 1 },
    target: { ...shaft(4), direction: 1 },
    maxGears: 5,
    maxBelts: 2,
    beltLinks: [belt(0, 2), belt(0, 3), belt(1, 3), belt(0, 4)],
  };
}
test("open belt transmits across gaps preserving direction while gear contacts flip", () => {
  const p = beltPuzzle();
  for (const bridge of [belt(0, 2), belt(2, 0)]) {
    const result = movementNetwork(p, [shaft(2), shaft(3)], [bridge]);
    assert.equal(result.blocked, false);
    assert.equal(result.directions.get("2,1"), 1);
    assert.equal(result.directions.get("3,1"), -1);
    assert.equal(result.directions.get("4,1"), 1);
  }
  assert.equal(gearDirections(p, [], [belt(0, 4)]).get("4,1"), 1);
});
test("signed networks stop conflicting cycles but allow consistent constraints", () => {
  const p = beltPuzzle(),
    gears = [shaft(1), shaft(2), shaft(3)];
  assert.equal(movementNetwork(p, gears, [belt(0, 2)]).blocked, false);
  const conflict = movementNetwork(p, gears, [belt(0, 3)]);
  assert.equal(conflict.blocked, true);
  assert.match(conflict.error!, /заблокирован/);
  assert.equal(conflict.directions.size, 0);
  assert.equal(gearDirections(p, gears, [belt(0, 3)]).size, 0);
});
test("belt preview rejects unknown shafts, duplicate pairs, limits and malformed inputs", () => {
  const p = beltPuzzle();
  assert.equal(movementNetwork(p, [shaft(3)], [belt(0, 2)]).blocked, true);
  assert.equal(movementNetwork(p, [], [belt(0, 4), belt(4, 0)]).blocked, true);
  assert.equal(
    movementNetwork(
      p,
      [shaft(1), shaft(3)],
      [belt(0, 3), belt(1, 3), belt(0, 4)],
    ).blocked,
    true,
  );
  assert.equal(movementNetwork(p, [shaft(1)], [belt(1, 4)]).blocked, true);
  assert.equal(movementNetwork(p, [shaft(1), shaft(1)], []).blocked, true);
  for (const invalid of [
    null,
    {},
    { from: shaft(0), to: shaft(5) },
    { from: shaft(0), to: shaft(0) },
    { from: shaft(0), to: shaft(4), extra: true },
  ])
    assert.equal(movementNetwork(p, [], [invalid as Belt]).blocked, true);
  for (const missing of ["maxBelts", "beltLinks"] as const) {
    const legacy = { ...p };
    delete legacy[missing];
    assert.equal(movementNetwork(legacy, [], [belt(0, 4)]).blocked, true);
    assert.equal(
      gearDirections(legacy, [shaft(1), shaft(2), shaft(3)]).get("4,1"),
      1,
    );
  }
});
