import { useEffect, useRef, useState, type ReactNode } from "react";
import { GameScene, GameSprite, spriteFor } from "./GameSprite";
import type {
  DeliveryPuzzle,
  Belt,
  LabPuzzle,
  MovementPuzzle,
  Point,
  SignalPuzzle,
  Rule,
  Task,
} from "./types";
import { gearDirections, runSignal, same } from "./mechanics";
import { movementBoardGeometry } from "./boardGeometry";

export function Board({
  task,
  height,
  children,
  className = "",
  label,
}: {
  task: Task;
  height: number;
  children: ReactNode;
  className?: string;
  label: string;
}) {
  const element = useRef<HTMLDivElement>(null),
    [scale, setScale] = useState(1);
  useEffect(() => {
    const target = element.current;
    if (!target) return;
    const measure = () => setScale(target.clientWidth / 358);
    measure();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", measure);
      return () => window.removeEventListener("resize", measure);
    }
    const observer = new ResizeObserver(measure);
    observer.observe(target);
    return () => observer.disconnect();
  }, []);
  return (
    <div
      ref={element}
      className={`v5-board ${className}`}
      style={{ aspectRatio: `358 / ${height}` }}
    >
      <GameScene task={task} label={label}>
        <div
          className="v5-board-canvas"
          style={{ width: 358, height, transform: `scale(${scale})` }}
        >
          {children}
        </div>
      </GameScene>
    </div>
  );
}

function Sprite({
  task,
  role,
  fallback,
  x,
  y,
  size,
  className = "",
}: {
  task: Task;
  role: string;
  fallback: string;
  x: number;
  y: number;
  size: number;
  className?: string;
}) {
  return (
    <GameSprite
      spriteId={spriteFor(task, role, fallback)}
      className={`v5-object ${className}`}
      style={{ left: x, top: y, width: size, height: size }}
    />
  );
}

export function SignalBoard({
  task,
  step = 0,
  output,
  running = false,
  solved = false,
  rules = [],
}: {
  task: Task;
  step?: number;
  output?: string;
  running?: boolean;
  solved?: boolean;
  rules?: Rule[];
}) {
  const p = task.puzzle as SignalPuzzle;
  const result = solved ? runSignal(p, rules) : [];
  const first = solved
      ? p.stream[result.find((row) => row.output === "left")?.index ?? -1]
      : p.stream[step % p.stream.length],
    second = solved
      ? p.stream[result.find((row) => row.output === "right")?.index ?? -1]
      : p.stream.length > 1
        ? p.stream[(step + 1) % p.stream.length]
        : undefined;
  const bottle = (item: typeof first, index: number) => {
    const fallback =
      item.color === "red"
        ? "automation-bottle-circle"
        : "automation-bottle-square";
    const left = solved ? index === 0 : output === "left";
    const arrived = solved || (index === 0 && output);
    return (
      <div
        key={index}
        className="v5-signal-item"
        style={{
          left: arrived ? (left ? 32 : 230) : index === 0 ? 81 : 181,
          top: arrived ? (solved ? 264 : 287) : 29,
        }}
      >
        <GameSprite
          spriteId={spriteFor(task, `item:${item.color}`, fallback)}
        />
        {!solved && (
          <span className={`v5-item-trait ${item.color}`}>
            {item.color === "red"
              ? "красная"
              : item.color === "blue"
                ? "синяя"
                : item.color}
            {item.marked ? " · ●" : " · ○"}
          </span>
        )}
      </div>
    );
  };
  return (
    <Board
      task={task}
      height={solved ? 407 : 441}
      className={`v5-signal-board ${running ? "is-running" : ""}`}
      label="Поток упаковок, датчик и два выхода"
    >
      <div
        style={{
          transform: solved ? "scaleY(.923)" : undefined,
          transformOrigin: "top left",
        }}
      >
        <img
          className="v5-primitive"
          src="/assets/games-v5/automation-track-base.svg"
          width="242"
          height="344"
          style={{ left: 58, top: 39.68 }}
          alt=""
        />
        <img
          className="v5-primitive"
          src="/assets/games-v5/automation-track-edge.svg"
          width="232"
          height="334"
          style={{ left: 63, top: 44.68 }}
          alt=""
        />
        <img
          className="v5-primitive"
          src="/assets/games-v5/automation-track-surface.svg"
          width="225"
          height="327"
          style={{ left: 66.5, top: 48.18 }}
          alt=""
        />
        <img
          className="v5-primitive"
          src="/assets/games-v5/automation-track-dashes.svg"
          width="201"
          height="301"
          style={{ left: 78.5, top: 61.18 }}
          alt=""
        />
      </div>
      <Sprite
        task={task}
        role="tray"
        fallback="automation-tray"
        x={20}
        y={solved ? 277 : 300}
        size={120}
      />
      <Sprite
        task={task}
        role="tray"
        fallback="automation-tray"
        x={218}
        y={solved ? 277 : 300}
        size={120}
      />
      <Sprite
        task={task}
        role="scanner"
        fallback="automation-scanner"
        x={119}
        y={solved ? 126 : 137}
        size={120}
      />
      <span
        className="v5-output-label"
        style={{ left: 16, top: solved ? 253 : 276 }}
      >
        А ●
      </span>
      <span
        className="v5-output-label"
        style={{ right: 16, top: solved ? 253 : 276 }}
      >
        Б ■
      </span>
      {first && bottle(first, 0)}
      {second && bottle(second, 1)}
    </Board>
  );
}

export function MovementBoard({
  task,
  gears,
  running = false,
  busy = false,
  onToggle,
  selected,
  onSelect,
  belts = [],
  beltMode = false,
  beltStart,
  onShaft,
  onRemoveBelt,
  solved = false,
}: {
  task: Task;
  gears: Point[];
  running?: boolean;
  busy?: boolean;
  onToggle?: (point: Point) => void;
  selected?: Point | null;
  onSelect?: (point: Point) => void;
  belts?: Belt[];
  beltMode?: boolean;
  beltStart?: Point | null;
  onShaft?: (point: Point) => void;
  onRemoveBelt?: (index: number) => void;
  solved?: boolean;
}) {
  const p = task.puzzle as MovementPuzzle,
    directions = gearDirections(p, gears, belts);
  const { position, scale, x, y } = movementBoardGeometry(p, selected);
  return (
    <Board
      task={task}
      height={solved ? 383 : 462}
      className="v5-movement-board"
      label="Узлы передачи вращения"
    >
      <div
        className="v5-mechanism"
        style={{
          transform: `translate(${x + (solved ? 30.4 : 0)}px,${y}px) scale(${scale * (solved ? 0.83 : 1)})`,
          transformOrigin: "top left",
        }}
      >
        <img
          className="v5-primitive"
          src="/assets/games-v5/mechanics-track.svg"
          width="262"
          height="260"
          style={{ left: 48, top: 90 }}
          alt=""
        />
        <svg className="v5-belts" width="358" height="462" aria-hidden="true">
          {belts.map((belt, i) => {
            const from = position(belt.from),
              to = position(belt.to);
            return (
              <g key={i}>
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="#1e0e16"
                  strokeWidth="16"
                />
                <line
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke="#a2aaad"
                  strokeWidth="4"
                />
              </g>
            );
          })}
        </svg>
        {Array.from({ length: p.width * p.height }, (_, i) => {
          const point = { x: i % p.width, y: Math.floor(i / p.width) },
            source = same(point, p.source),
            target = same(point, p.target),
            placed = gears.some((g) => same(g, point)),
            focused = selected && same(point, selected),
            center = position(point),
            direction = directions.get(`${point.x},${point.y}`);
          if (solved && !source && !target && !placed) return null;
          const beltAllowed =
            beltMode &&
            beltStart &&
            p.beltLinks?.some(
              (link) =>
                (same(link.from, beltStart) && same(link.to, point)) ||
                (same(link.to, beltStart) && same(link.from, point)),
            );
          const size =
            solved || source || target ? 144 : placed ? 88 : focused ? 144 : 56;
          const sprite = source
            ? "mechanics-gear-ivory"
            : target
              ? "mechanics-gear-silver"
              : placed
                ? "mechanics-gear-red"
                : "mechanics-socket";
          return (
            <button
              key={i}
              className={`v5-gear-node ${source || target ? "is-fixed" : ""} ${beltMode ? "belt-mode" : ""} ${placed ? "is-placed" : "is-empty"} ${focused ? "is-selected" : ""} ${beltStart && same(point, beltStart) ? "belt-start" : ""} ${beltAllowed ? "belt-allowed" : ""}`}
              style={{
                left: center.x - size / 2,
                top: center.y - size / 2,
                width: size,
                height: size,
                zIndex: source || target ? 3 : focused || placed ? 4 : 2,
              }}
              disabled={
                busy ||
                solved ||
                (beltMode ? !(source || target || placed) : source || target) ||
                !onToggle
              }
              aria-pressed={
                beltMode
                  ? Boolean(beltStart && same(point, beltStart))
                  : Boolean(placed || focused)
              }
              aria-label={`${beltMode ? "Выбрать вал для ремня" : source ? "Привод" : target ? "Выход" : placed ? "Снять шестерню" : "Выбрать свободный узел"}, столбец ${point.x + 1}, ряд ${point.y + 1}${direction ? (direction === 1 ? ", по часовой стрелке" : ", против часовой стрелки") : ""}${beltAllowed ? ", доступен для соединения" : ""}`}
              onClick={() => {
                if (beltMode) onShaft?.(point);
                else if (placed) onToggle?.(point);
                else if (onSelect) onSelect(point);
                else onToggle?.(point);
              }}
            >
              <GameSprite
                spriteId={spriteFor(
                  task,
                  source
                    ? "source"
                    : target
                      ? "target"
                      : placed
                        ? "gear"
                        : "socket",
                  sprite,
                )}
                className={running && direction ? "v5-rotating" : ""}
                style={{
                  animationDirection: direction === -1 ? "reverse" : "normal",
                }}
              />
              {!source && !target && !placed && (
                <span className="v5-socket-plus">+</span>
              )}
            </button>
          );
        })}
      </div>
      {!solved && (
        <>
          <img
            className="v5-primitive"
            src="/assets/games-v5/mechanics-spare-slot.svg"
            width="113"
            height="113"
            style={{ left: 19.5, top: 325.5 }}
            alt=""
          />
          <Sprite
            task={task}
            role="gear"
            fallback="mechanics-gear-red"
            x={28}
            y={330}
            size={96}
          />
        </>
      )}
      {belts.length > 0 && onRemoveBelt && (
        <div className="v5-belt-removal">
          {belts.map((_, i) => (
            <button
              type="button"
              key={i}
              disabled={busy}
              onClick={() => onRemoveBelt(i)}
            >
              Снять ремень {i + 1}
            </button>
          ))}
        </div>
      )}
    </Board>
  );
}

export function LabBoard({
  task,
  revealed,
  excluded,
  sampleId,
  busy = false,
  onSelect,
  solved = false,
}: {
  task: Task;
  revealed: string[];
  excluded: string[];
  sampleId: string;
  busy?: boolean;
  onSelect?: (id: string) => void;
  solved?: boolean;
}) {
  const p = task.puzzle as LabPuzzle;
  return (
    <Board
      task={task}
      height={
        solved
          ? Math.max(407, 175 + Math.ceil(p.samples.length / 2) * 116)
          : Math.max(468, 200 + Math.ceil(p.samples.length / 2) * 134)
      }
      className={`v5-lab-board ${solved ? "is-solved" : ""}`}
      label="Неизвестный образец и справочник образцов"
    >
      <span className="v5-vial-shadow" />
      <Sprite
        task={task}
        role="meter"
        fallback="laboratory-meter"
        x={238}
        y={74}
        size={112}
      />
      <Sprite
        task={task}
        role="dropper"
        fallback="laboratory-dropper"
        x={14}
        y={83}
        size={96}
      />
      <Sprite
        task={task}
        role={revealed.length ? "testedSample" : "unknownSample"}
        fallback={
          revealed.length ? "laboratory-tube-gold" : "laboratory-tube-red"
        }
        x={107}
        y={12}
        size={144}
      />
      {p.samples.map((sample, i) => {
        const incompatible = revealed.some(
            (id) => sample.properties[id] !== p.observations[id],
          ),
          removed = excluded.includes(sample.id) || incompatible,
          selected = sampleId === sample.id;
        return (
          <button
            key={sample.id}
            className={`v5-sample ${removed ? "excluded" : ""} ${selected ? "selected" : ""}`}
            style={{
              left: i % 2 ? 194 : 20,
              top:
                (solved ? 179 : 206) + Math.floor(i / 2) * (solved ? 116 : 134),
            }}
            disabled={
              busy || solved || !onSelect || excluded.includes(sample.id)
            }
            aria-pressed={selected}
            aria-label={`${sample.name}${incompatible ? ", не совпадает с открытыми свойствами" : ""}`}
            onClick={() => onSelect?.(sample.id)}
          >
            <GameSprite
              spriteId={spriteFor(
                task,
                solved && selected ? "matchedSample" : `sample:${sample.id}`,
                solved && selected
                  ? "laboratory-tube-gold"
                  : "laboratory-tube-red",
              )}
            />
            <span>
              <strong>{sample.name}</strong>
              <small>
                {p.tests
                  .slice(0, 2)
                  .map((test) => sample.properties[test.id])
                  .join(" · ")}
              </small>
            </span>
          </button>
        );
      })}
    </Board>
  );
}

export function DeliveryBoard({
  task,
  route,
  selected,
  chosen,
  busy = false,
  onCell,
  solved = false,
}: {
  task: Task;
  route: Point[];
  selected?: string;
  chosen: string[];
  busy?: boolean;
  onCell?: (point: Point, stockId?: string) => void;
  solved?: boolean;
}) {
  const p = task.puzzle as DeliveryPuzzle,
    width = p.warehouse.width,
    height = p.warehouse.height;
  return (
    <Board
      task={task}
      height={solved ? 407 : 465}
      className="v5-delivery-board"
      label="Склад: партии, резерв и маршрут"
    >
      <div
        className="v5-warehouse-cells"
        style={{
          gridTemplateColumns: `repeat(${width}, minmax(0, 1fr))`,
          gridTemplateRows: `repeat(${height}, minmax(0, 1fr))`,
        }}
      >
        {Array.from({ length: width * height }, (_, i) => {
          const point = { x: i % width, y: Math.floor(i / width) },
            stock = p.batches.find((b) => same(b.location, point)),
            onRoute = route.some((r) => same(r, point)),
            last = same(route.at(-1) ?? p.start, point),
            start = same(p.start, point),
            productIndex = stock
              ? p.order.findIndex((o) => o.product === stock.product)
              : 0;
          const sprite =
            productIndex === 1 ? "warehouse-crate-b" : "warehouse-crate-a";
          return (
            <button
              key={i}
              className={`${onRoute ? "on-route" : ""} ${stock?.reserved ? "reserved" : ""} ${stock && (selected === stock.id || chosen.includes(stock.id)) ? "chosen" : ""}`}
              aria-label={`${start ? "Вход, " : ""}столбец ${point.x + 1}, ряд ${point.y + 1}${stock ? `, партия ${stock.id}${stock.reserved ? ", резерв" : ""}` : ""}${onRoute ? ", маршрут" : ""}`}
              disabled={busy || solved || !onCell}
              onClick={() => onCell?.(point, stock?.id)}
            >
              {stock && (
                <>
                  <GameSprite
                    spriteId={spriteFor(task, `batch:${stock.id}`, sprite)}
                  />
                  <span className="v5-stock-name">
                    {stock.id.toUpperCase()}
                  </span>
                  {stock.reserved && (
                    <GameSprite
                      spriteId={spriteFor(task, "barrier", "warehouse-barrier")}
                      className="v5-stock-barrier"
                    />
                  )}
                </>
              )}
              {(last || (!route.length && start)) && (
                <GameSprite
                  spriteId={spriteFor(task, "carrier", "warehouse-pallet-jack")}
                  className="v5-carrier"
                />
              )}
              {onRoute && !last && !stock && (
                <span className="v5-route-dot" aria-hidden="true">
                  ●
                </span>
              )}
              {stock?.reserved && (
                <small className="v5-reserved-label">РЕЗЕРВ</small>
              )}
            </button>
          );
        })}
      </div>
    </Board>
  );
}
