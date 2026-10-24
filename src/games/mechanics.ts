import type {
  Batch,
  Belt,
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
export function movementNetwork(
  puzzle: MovementPuzzle,
  gears: Point[],
  belts: Belt[] = [],
) {
  const stopped = (error: string) => ({
    directions: new Map<string, number>(),
    blocked: true,
    error,
  });
  const key = (point: Point) => `${point.x},${point.y}`;
  const validPoint = (point: Point) =>
    point &&
    Number.isInteger(point.x) &&
    Number.isInteger(point.y) &&
    point.x >= 0 &&
    point.y >= 0 &&
    point.x < puzzle.width &&
    point.y < puzzle.height;
  if (
    !Array.isArray(gears) ||
    !Array.isArray(belts) ||
    gears.length > puzzle.maxGears
  )
    return stopped("Некорректные детали механизма.");
  const nodes = [puzzle.source, ...gears, puzzle.target];
  if (
    nodes.some((point) => !validPoint(point)) ||
    new Set(nodes.map(key)).size !== nodes.length
  )
    return stopped("Валы должны занимать разные клетки внутри поля.");
  const pair = (belt: Belt) => {
    if (
      !belt ||
      typeof belt !== "object" ||
      Array.isArray(belt) ||
      Object.keys(belt).sort().join(",") !== "from,to"
    )
      return null;
    if (
      ![belt.from, belt.to].every(
        (point) =>
          point &&
          typeof point === "object" &&
          !Array.isArray(point) &&
          Object.keys(point).sort().join(",") === "x,y" &&
          validPoint(point),
      ) ||
      same(belt.from, belt.to)
    )
      return null;
    return [key(belt.from), key(belt.to)].sort().join("|");
  };
  const allowed = new Set<string>();
  if (belts.length) {
    if (
      !Number.isInteger(puzzle.maxBelts) ||
      puzzle.maxBelts! <= 0 ||
      !Array.isArray(puzzle.beltLinks)
    )
      return stopped("В этом уровне ремни не предусмотрены.");
    if (belts.length > puzzle.maxBelts!)
      return stopped("Превышено доступное количество ремней.");
    for (const link of puzzle.beltLinks) {
      const linkKey = pair(link);
      if (!linkKey) return stopped("Некорректные допустимые связи механизма.");
      allowed.add(linkKey);
    }
  }
  const edges = new Map(
    nodes.map((point) => [
      key(point),
      [] as { to: string; multiplier: number }[],
    ]),
  );
  function edge(from: Point, to: Point, multiplier: number) {
    edges.get(key(from))!.push({ to: key(to), multiplier });
    edges.get(key(to))!.push({ to: key(from), multiplier });
  }
  for (const [index, point] of nodes.entries())
    for (const other of nodes.slice(index + 1))
      if (distance(point, other) === 1) edge(point, other, -1);
  const seen = new Set<string>();
  for (const belt of belts) {
    const beltKey = pair(belt);
    if (
      !beltKey ||
      seen.has(beltKey) ||
      !allowed.has(beltKey) ||
      !edges.has(key(belt.from)) ||
      !edges.has(key(belt.to))
    )
      return stopped(
        "Ремень должен соединять разрешённую пару существующих валов без повторов.",
      );
    seen.add(beltKey);
    edge(belt.from, belt.to, 1);
  }
  const directions = new Map([[key(puzzle.source), puzzle.source.direction]]);
  const queue = [key(puzzle.source)];
  while (queue.length) {
    const point = queue.shift()!;
    for (const { to, multiplier } of edges.get(point)!) {
      const direction = directions.get(point)! * multiplier;
      if (directions.has(to) && directions.get(to) !== direction)
        return stopped("Механизм заблокирован противоположными передачами.");
      if (!directions.has(to)) {
        directions.set(to, direction);
        queue.push(to);
      }
    }
  }
  return { directions, blocked: false, error: undefined };
}
export function gearDirections(
  puzzle: MovementPuzzle,
  gears: Point[],
  belts: Belt[] = [],
) {
  return movementNetwork(puzzle, gears, belts).directions;
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
