import type { MovementPuzzle, Point } from "./types";

/** Keep the reference layout when it fits, and fit taller/wider level fields. */
export function movementBoardGeometry(
  puzzle: MovementPuzzle,
  selected?: Point | null,
) {
  const position = (point: Point) => ({
    x:
      88 +
      (point.x / Math.max(1, puzzle.width - 1)) * 182 +
      (point.y - puzzle.source.y) * 36,
    y:
      130 +
      (point.x / Math.max(1, puzzle.width - 1)) * 180 -
      (point.y - puzzle.source.y) * 36,
  });
  const bounds = Array.from(
    { length: puzzle.width * puzzle.height },
    (_, index) => {
      const point = {
          x: index % puzzle.width,
          y: Math.floor(index / puzzle.width),
        },
        center = position(point);
      const fixed = [puzzle.source, puzzle.target, selected].some(
        (p) => p && p.x === point.x && p.y === point.y,
      );
      const radius = fixed ? 72 : 44;
      return {
        left: center.x - radius,
        right: center.x + radius,
        top: center.y - radius,
        bottom: center.y + radius,
      };
    },
  );
  const left = Math.min(...bounds.map((b) => b.left)),
    right = Math.max(...bounds.map((b) => b.right)),
    top = Math.min(...bounds.map((b) => b.top)),
    bottom = Math.max(...bounds.map((b) => b.bottom));
  const scale = Math.min(1, 342 / (right - left), 446 / (bottom - top));
  const x =
    left * scale < 8
      ? 8 - left * scale
      : right * scale > 350
        ? 350 - right * scale
        : 0;
  const y =
    top * scale < 8
      ? 8 - top * scale
      : bottom * scale > 454
        ? 454 - bottom * scale
        : 0;
  return { position, scale, x, y };
}
