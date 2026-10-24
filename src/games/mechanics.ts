import type {
  Batch,
  MovementPuzzle,
  Placement,
  Point,
  Rule,
  SignalPuzzle,
} from "./types";
export const same = (a: Point, b: Point) => a.x === b.x && a.y === b.y;
export const distance = (a: Point, b: Point) =>
  Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
export function runSignal(puzzle: SignalPuzzle, rules: Rule[]) {
  return puzzle.stream.map((item, index) => {
    const ruleIndex = rules.findIndex(
      (rule) =>
        rule.condition === "always" ||
        rule.condition === item.color ||
        (rule.condition === "marked" && item.marked) ||
        (rule.condition === "unmarked" && !item.marked) ||
        (rule.condition === "red_marked" &&
          item.color === "red" &&
          item.marked),
    );
    const output = rules[ruleIndex]?.output;
    const expected = (
      puzzle.rule === "color"
        ? item.color === "red"
        : puzzle.rule === "mark"
          ? item.marked
          : item.color === "red" && item.marked
    )
      ? "left"
      : "right";
    return { index, ruleIndex, output, expected, correct: output === expected };
  });
}
export function gearDirections(puzzle: MovementPuzzle, gears: Point[]) {
  const nodes = [puzzle.source, ...gears, puzzle.target],
    directions = new Map<string, number>();
  const key = (p: Point) => `${p.x},${p.y}`;
  directions.set(key(puzzle.source), puzzle.source.direction);
  const queue = [puzzle.source];
  while (queue.length) {
    const point = queue.shift()!;
    for (const node of nodes)
      if (distance(point, node) === 1 && !directions.has(key(node))) {
        directions.set(key(node), -directions.get(key(point))!);
        queue.push(node as typeof puzzle.source);
      }
  }
  return directions;
}
export function footprint(batch: Batch, placement: Placement): Point[] {
  return batch.cells.map(([dx, dy]) => ({
    x: placement.x + (placement.rotated ? dy : dx),
    y: placement.y + (placement.rotated ? dx : dy),
  }));
}
export function placementError(
  batch: Batch,
  placement: Placement,
  placements: Placement[],
  batches: Batch[],
  width: number,
  height: number,
) {
  if (batch.reserved) return "Эта партия зарезервирована.";
  const cells = footprint(batch, placement);
  if (cells.some((p) => p.x < 0 || p.y < 0 || p.x >= width || p.y >= height))
    return "Упаковка выходит за край площадки. Попробуй повернуть её.";
  const occupied = placements
    .filter((p) => p.batchId !== placement.batchId)
    .flatMap((p) =>
      footprint(
        batches.find((b) => b.id === p.batchId)!,
        p,
      ),
    );
  if (cells.some((p) => occupied.some((o) => same(p, o))))
    return "На этом месте уже стоит другая упаковка.";
  return null;
}
export function appendRoute(route: Point[], point: Point): Point[] | null {
  if (distance(route.at(-1)!, point) !== 1) return null;
  return [...route, point];
}
