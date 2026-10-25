import type { ShiftPuzzle, ShiftSchemeNode } from "./ShiftTypes";

export const SHIFT_SCHEME_SIZE = { width: 350, height: 270 };
type Point = { x: number; y: number };
export type ShiftNodeLayout = {
  node: ShiftSchemeNode;
  display: "card" | "queue" | "extra";
  x: number;
  y: number;
  width: number;
  height: number;
  connection: Point;
};
const legacyPositions: Record<string, Point> = {
  feed: { x: 30, y: 33 }, capping: { x: 30, y: 112 },
  packaging: { x: 195, y: 192 }, queue: { x: 180, y: 133 },
};
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(value, high));
const finite = (value: number | undefined, fallback: number) =>
  typeof value === "number" && Number.isFinite(value) ? value : fallback;

function nodeLayout(node: ShiftSchemeNode, index: number, extraIndex: number): ShiftNodeLayout {
  const display = node.display ??
    (node.id === "queue" ? "queue" : node.position || legacyPositions[node.id] ? "card" : "extra");
  const width = display === "card" ? 125 : display === "queue" ? 150 : 140;
  const height = display === "card" ? 56 : display === "queue" ? 34 : 12;
  const fallback = legacyPositions[node.id] ?? (display === "extra"
    ? { x: 192.5, y: 255 - extraIndex * 16 }
    : { x: 24 + (index % 2) * 174, y: 32 + Math.floor(index / 2) * 80 });
  const x = clamp(finite(node.position?.x, fallback.x), 0, SHIFT_SCHEME_SIZE.width - width);
  const y = clamp(finite(node.position?.y, fallback.y), 0, SHIFT_SCHEME_SIZE.height - height);
  // The original queue caption sits above/right of its items. Move both
  // together when its position changes, retaining the existing four-dot buffer.
  const connection = display === "queue"
    ? { x: clamp(x - 52, 40, 310), y: clamp(y + 87, 14, 256) }
    : { x: x + width / 2, y: y + height / 2 };
  return { node, display, x, y, width, height, connection };
}

function port(node: ShiftNodeLayout, other: ShiftNodeLayout) {
  if (node.display === "queue") return { ...node.connection, axis: "point" as const };
  const dx = other.connection.x - node.connection.x, dy = other.connection.y - node.connection.y;
  return Math.abs(dx) > Math.abs(dy)
    ? { x: dx >= 0 ? node.x + node.width : node.x, y: node.y + node.height / 2, axis: "horizontal" as const }
    // The established vertical pipe passes 43.5px from a card's left edge.
    : { x: node.x + node.width * (43.5 / 125), y: dy >= 0 ? node.y + node.height : node.y, axis: "vertical" as const };
}

function midpoint(points: Point[]): Point {
  const lengths = points.slice(1).map((point, index) => Math.hypot(point.x - points[index].x, point.y - points[index].y));
  let remaining = lengths.reduce((sum, length) => sum + length, 0) / 2;
  for (let index = 0; index < lengths.length; index++) {
    const length = lengths[index];
    if (remaining <= length && length > 0) {
      const ratio = remaining / length;
      return { x: points[index].x + (points[index + 1].x - points[index].x) * ratio,
        y: points[index].y + (points[index + 1].y - points[index].y) * ratio };
    }
    remaining -= length;
  }
  return points[0];
}

export function shiftSchemeGeometry(scheme: ShiftPuzzle["scheme"]) {
  let extraIndex = 0;
  const nodes = scheme.nodes.map((node, index) => {
    const layout = nodeLayout(node, index, extraIndex);
    if (layout.display === "extra") extraIndex++;
    return layout;
  });
  const byId = new Map(nodes.map((node) => [node.node.id, node]));
  const flows = scheme.flows.flatMap((flow) => {
    const from = byId.get(flow.from), to = byId.get(flow.to);
    if (!from || !to || from === to) return [];
    const start = port(from, to), end = port(to, from);
    let points: Point[];
    if (start.x === end.x || start.y === end.y) points = [start, end];
    else if (start.axis === "vertical" && end.axis === "vertical") {
      const y = (start.y + end.y) / 2;
      points = [start, { x: start.x, y }, { x: end.x, y }, end];
    } else if (start.axis === "horizontal" && end.axis === "horizontal") {
      const x = (start.x + end.x) / 2;
      points = [start, { x, y: start.y }, { x, y: end.y }, end];
    } else points = [start, start.axis === "vertical" || end.axis === "horizontal"
      ? { x: start.x, y: end.y } : { x: end.x, y: start.y }, end];
    return [{ flow, fromLabel:from.node.label, toLabel:to.node.label, points, midpoint: midpoint(points), path: points.map((point, index) =>
      `${index ? "L" : "M"}${point.x},${point.y}`).join(" ") }];
  });
  const queues = nodes.filter((node) => node.display === "queue").map((layout) => ({
    nodeId: layout.node.id,
    dots: Array.from({ length: clamp(Math.floor(finite(layout.node.value, 0)), 0, 4) }, (_, index) => ({
      x: layout.connection.x - 33 + index * 22, y: layout.connection.y,
    })),
  }));
  return { nodes, flows, queues };
}
