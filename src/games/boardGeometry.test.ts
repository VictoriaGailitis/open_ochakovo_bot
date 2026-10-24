import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { movementBoardGeometry } from "./boardGeometry";
import type { MovementPuzzle, Point, Task } from "./types";

const tasks = (
  JSON.parse(
    readFileSync(new URL("../../server/catalog.json", import.meta.url), "utf8"),
  ) as { tasks: Task[] }
).tasks;

test("movement layout keeps reference source and target positions when the field fits", () => {
  const puzzle = tasks.find((t) => t.game === "movement")!
    .puzzle as MovementPuzzle;
  const geometry = movementBoardGeometry(puzzle, { x: 2, y: 1 });
  assert.equal(geometry.scale, 1);
  assert.equal(geometry.x, 0);
  assert.equal(geometry.y, 0);
  assert.deepEqual(geometry.position(puzzle.source), { x: 88, y: 130 });
  assert.deepEqual(geometry.position(puzzle.target), { x: 270, y: 310 });
});

function assertFits(puzzle: MovementPuzzle, selected?: Point) {
  const geometry = movementBoardGeometry(puzzle, selected);
  for (let y = 0; y < puzzle.height; y++)
    for (let x = 0; x < puzzle.width; x++) {
      const point = { x, y },
        center = geometry.position(point);
      const fixed = [puzzle.source, puzzle.target, selected].some(
        (p) => p && p.x === x && p.y === y,
      );
      const radius = (fixed ? 72 : 44) * geometry.scale;
      const cx = center.x * geometry.scale + geometry.x,
        cy = center.y * geometry.scale + geometry.y;
      assert.ok(
        cx - radius >= 7.999 && cx + radius <= 350.001,
        `${x},${y}: horizontal bounds`,
      );
      assert.ok(
        cy - radius >= 7.999 && cy + radius <= 454.001,
        `${x},${y}: vertical bounds`,
      );
    }
}

test("every configured movement level, including the displaced target, remains inside the scene", () => {
  for (const task of tasks.filter((t) => t.game === "movement")) {
    const puzzle = task.puzzle as MovementPuzzle;
    assertFits(puzzle);
    assertFits(puzzle, { x: puzzle.width - 1, y: 0 });
  }
});

test("new larger fields use puzzle geometry instead of a hardcoded level ID", () => {
  const puzzle: MovementPuzzle = {
    width: 9,
    height: 7,
    source: { x: 0, y: 3, direction: 1 },
    target: { x: 8, y: 6, direction: -1 },
    maxGears: 20,
  };
  assertFits(puzzle, { x: 0, y: 6 });
  const geometry = movementBoardGeometry(puzzle);
  assert.ok(geometry.scale < 1);
  const cells = new Set(
    Array.from({ length: puzzle.width * puzzle.height }, (_, i) => {
      const p = geometry.position({
        x: i % puzzle.width,
        y: Math.floor(i / puzzle.width),
      });
      return `${p.x},${p.y}`;
    }),
  );
  assert.equal(cells.size, puzzle.width * puzzle.height);
});
