import { useEffect, useRef, useState } from "react";
import { DraftConflictError, DraftSnapshotClock } from "../draftClock";
import type { CSSProperties } from "react";
import type {
  CompletionResult,
  Belt,
  DeliveryPuzzle,
  GamePlayerProps,
  HistoryPuzzle,
  LabPuzzle,
  MovementPuzzle,
  Placement,
  Point,
  Rule,
  SignalPuzzle,
  Task,
} from "./types";
import {
  appendRoute,
  footprint,
  movementNetwork,
  placementError,
  runSignal,
  same,
} from "./mechanics";
import {
  SignalBoard,
  MovementBoard,
  LabBoard,
  DeliveryBoard,
} from "./GameBoards";
import { ShiftGame } from "./ShiftGame";
import type { ShiftTask } from "./ShiftTypes";
import "./games.css";

type Draft = Record<string, unknown>;
type StandardTask = Task & { game: Exclude<Task["game"], "shift"> };
interface EditorProps {
  task: Task;
  draft: Draft;
  change: (draft: Draft) => void;
  submit: (solution: unknown) => void;
  busy: boolean;
}
const conditions: Record<string, string> = {
  red: "Красная упаковка",
  blue: "Синяя упаковка",
  marked: "Есть метка",
  unmarked: "Нет метки",
  red_marked: "Красная И с меткой",
  always: "Иначе / любая",
};
const products: Record<string, string> = {
  kvass: "Квас",
  water: "Вода",
  lemonade: "Лимонад",
};
const initials: Record<string, string> = {
  signal: "02",
  movement: "03",
  lab: "04",
  delivery: "05",
  history: "ТЕСТ",
};
function initial(task: StandardTask): Draft {
  switch (task.game) {
    case "signal":
      return { rules: [{ condition: "always", output: "left" }] };
    case "movement":
      return { gears: [], belts: [] };
    case "lab":
      return { revealed: [], evidence: [], excluded: [], sampleId: "" };
    case "delivery":
      return { placements: [], route: [(task.puzzle as DeliveryPuzzle).start] };
    case "history":
      return { answers: {}, index: 0 };
  }
}
const errorText = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Не удалось связаться с сервером. Попробуй ещё раз.";
export function GamePlayer(props: GamePlayerProps) {
  if (props.task.game === "shift") {
    return (
      <ShiftGame
        key={props.task.id}
        {...props}
        task={props.task as ShiftTask}
      />
    );
  }
  return (
    <GameSession
      key={props.task.id}
      {...props}
      task={props.task as StandardTask}
    />
  );
}
export default GamePlayer;
function GameSession({
  task,
  draft: saved,
  draftRevision = 0,
  onSave,
  onComplete,
  onCareer,
  onExit,
}: Omit<GamePlayerProps, "task"> & { task: StandardTask }) {
  const [draft, setDraft] = useState<Draft>(() => ({
    ...initial(task),
    ...(saved && typeof saved === "object" && !Array.isArray(saved)
      ? saved
      : {}),
  }));
  const [editing, setEditing] = useState(true);
  const [busy, setBusy] = useState(false),
    [result, setResult] = useState<CompletionResult | null>(null),
    [error, setError] = useState(""),
    [saveState, setSaveState] = useState("");
  const heading = useRef<HTMLHeadingElement>(null),
    previousSuccess = useRef(false);
  useEffect(() => {
    const correct = Boolean(result?.correct);
    if (correct || previousSuccess.current) {
      heading.current?.scrollIntoView({ block: "start", behavior: "auto" });
      heading.current?.focus({ preventScroll: true });
    }
    previousSuccess.current = correct;
  }, [result?.correct]);
  const saveRef = useRef(onSave),
    latest = useRef(draft),
    saveQueue = useRef(Promise.resolve()),
    mounted = useRef(true),
    shouldSave = useRef(false);
  const snapshotClock = useRef<DraftSnapshotClock<Draft> | null>(null);
  if (!snapshotClock.current)
    snapshotClock.current = new DraftSnapshotClock(draft, draftRevision);
  saveRef.current = onSave;
  latest.current = draft;
  shouldSave.current = editing && !result?.correct;
  useEffect(() => {
    mounted.current = true;
    // Start the keepalive request synchronously while pagehide is dispatched.
    const saveBeforeReload = () => {
      if (shouldSave.current)
        void saveRef
          .current(
            latest.current,
            snapshotClock.current!.revisionOf(latest.current),
          )
          .catch(() => undefined);
    };
    window.addEventListener("pagehide", saveBeforeReload);
    return () => {
      window.removeEventListener("pagehide", saveBeforeReload);
      mounted.current = false;
      if (shouldSave.current)
        void persist(latest.current).catch(() => undefined);
    };
  }, []);
  function persist(value: Draft) {
    const revision = snapshotClock.current!.revisionOf(value);
    const operation = saveQueue.current
      .catch(() => undefined)
      .then(() => saveRef.current(value, revision))
      .catch((error) => {
        if (error instanceof DraftConflictError && latest.current === value) {
          const restored = {
            ...initial(task),
            ...(error.draft &&
            typeof error.draft === "object" &&
            !Array.isArray(error.draft)
              ? error.draft
              : {}),
          };
          snapshotClock.current!.restore(restored, error.revision);
          latest.current = restored;
          if (mounted.current) {
            setDraft(restored);
            setError(
              "Черновик изменён в другой вкладке. Загружена актуальная версия сервера; проверь данные.",
            );
          }
        }
        throw error;
      });
    saveQueue.current = operation;
    return operation;
  }
  useEffect(() => {
    if (!editing || result?.correct) return;
    setSaveState("Сохраняем…");
    const timer = setTimeout(() => {
      void persist(draft)
        .then(() => {
          if (mounted.current) setSaveState("Прогресс сохранён");
        })
        .catch(() => {
          if (mounted.current) setSaveState("Не сохранено — повторить");
        });
    }, 650);
    return () => clearTimeout(timer);
  }, [draft, editing, result?.correct]);
  async function submit(solution: unknown) {
    if (busy) return;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      await persist(latest.current);
      const completion = await onComplete(solution);
      if (mounted.current) setResult(completion);
    } catch (e) {
      if (mounted.current) setError(errorText(e));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  async function leave() {
    if (busy) return;
    setBusy(true);
    try {
      if (editing && !result?.correct) await persist(latest.current);
      onExit();
    } catch (e) {
      setError(errorText(e));
      setBusy(false);
    }
  }
  const change = (value: Draft) => {
    snapshotClock.current!.edit(value);
    latest.current = value;
    setDraft(value);
    setResult(null);
    setError("");
  };
  const editor = {
    task,
    draft,
    change,
    submit: (solution: unknown) => {
      void submit(solution);
    },
    busy,
  };
  const solved = Boolean(result?.correct);
  const position = task.game === "history" ? 0 : Number(initials[task.game]);
  const successTitles: Record<string, string> = {
    signal: "Поток собран!",
    movement: "Движение передано!",
    lab: "Образец найден!",
    delivery: "Заказ доставлен!",
    history: "История открыта!",
  };
  const principleTitles: Record<string, string> = {
    signal: "Сигнал → правило → действие",
    movement: "Шестерни меняют направление, открытый ремень сохраняет",
    lab: "Наблюдение → сравнение → вывод",
    delivery: "Заказ → размещение → маршрут",
    history: "У истории есть продолжение",
  };
  return (
    <section
      className={`game-player v5-game v5-${task.game}`}
      aria-label={task.title}
    >
      <header className="v5-game-header">
        <h1 ref={heading} tabIndex={-1}>
          {solved ? successTitles[task.game] : task.title}
        </h1>
        <button
          type="button"
          className="v5-game-close"
          aria-label="Закрыть игру и сохранить прогресс"
          disabled={busy}
          onClick={() => {
            void leave();
          }}
        >
          ×
        </button>
      </header>
      <p className="v5-game-meta">
        {task.game === "history" ? "ТЕСТ" : `${initials[task.game]} / 05`} ·{" "}
        {solved
          ? "УРОВЕНЬ ПРОЙДЕН"
          : `УРОВЕНЬ ${String(task.level).padStart(2, "0")}`}{" "}
        ·{" "}
        {solved
          ? result?.alreadyCompleted
            ? "БАЛЛЫ УЖЕ НАЧИСЛЕНЫ"
            : `+${result?.pointsAwarded} БАЛЛОВ`
          : `+${task.points} БАЛЛОВ`}
      </p>
      {position > 0 && (
        <div className="v5-route-progress" aria-label={`Игра ${position} из 5`}>
          {Array.from({ length: 5 }, (_, i) => (
            <span key={i} className={i < position ? "filled" : ""} />
          ))}
        </div>
      )}
      {!solved ? (
        <div className="game-editor" aria-busy={busy}>
          {task.game === "signal" ? (
            <Signal {...editor} />
          ) : task.game === "movement" ? (
            <Movement {...editor} />
          ) : task.game === "lab" ? (
            <Lab {...editor} />
          ) : task.game === "delivery" ? (
            <Delivery {...editor} />
          ) : (
            <History {...editor} />
          )}
        </div>
      ) : (
        <>
          {task.game === "signal" && (
            <SignalBoard task={task} rules={draft.rules as Rule[]} solved />
          )}
          {task.game === "movement" && (
            <MovementBoard
              task={task}
              gears={draft.gears as Point[]}
              belts={(draft.belts ?? []) as Belt[]}
              solved
              running
            />
          )}
          {task.game === "lab" && (
            <LabBoard
              task={task}
              revealed={draft.revealed as string[]}
              excluded={draft.excluded as string[]}
              sampleId={draft.sampleId as string}
              solved
            />
          )}
          {task.game === "delivery" && (
            <DeliveryBoard
              task={task}
              route={draft.route as Point[]}
              chosen={(draft.placements as Placement[]).map((p) => p.batchId)}
              solved
            />
          )}
          <div className="v5-feedback-card" role="status">
            <span className="game-eyebrow">
              {task.game === "signal"
                ? "ПРИНЦИП АВТОМАТИЗАЦИИ"
                : task.game === "movement"
                  ? "ПРИНЦИП МЕХАНИКИ"
                  : task.game === "lab"
                    ? "ЛАБОРАТОРНОЕ ИССЛЕДОВАНИЕ"
                    : task.game === "delivery"
                      ? "ПРИНЦИП ЛОГИСТИКИ"
                      : "ИСТОРИЯ КОМПАНИИ"}
            </span>
            <h2>{principleTitles[task.game]}</h2>
            <p>{result?.explanation || task.explanation}</p>
          </div>
          <button
            className="game-primary"
            onClick={() => {
              setResult(null);
              setEditing(true);
            }}
          >
            Ещё одна попытка
          </button>
          <button
            className="game-secondary"
            onClick={() => onCareer(task.direction)}
          >
            Познакомиться с профессией →
          </button>
        </>
      )}
      {error && (
        <p role="alert" className="game-error">
          {error}
        </p>
      )}
      {result && !solved && (
        <div className="game-error" role="alert">
          <h2>Пока не сходится</h2>
          {(result.errors ?? []).map((message, i) => (
            <p key={i}>{message}</p>
          ))}
        </div>
      )}
      {!solved && (
        <button
          className="game-save-state"
          disabled={busy}
          onClick={() => {
            setSaveState("Сохраняем…");
            void persist(latest.current)
              .then(() => setSaveState("Прогресс сохранён"))
              .catch((e) => {
                setSaveState("Не сохранено — повторить");
                setError(errorText(e));
              });
          }}
          aria-live="polite"
        >
          {saveState || "Сохранить прогресс"}
        </button>
      )}
      <details className="game-help">
        <summary>Задача и управление</summary>
        <p>{task.description}</p>
        <p>
          {task.game === "signal"
            ? "Для каждой упаковки срабатывает первое подходящее правило. Добавляй и переставляй блоки, затем проверь пробный поток."
            : task.game === "movement"
              ? "Выбери свободный узел и установи шестерню. Нажатие на установленную деталь убирает её. Соедини привод и выход; каждое зацепление меняет направление. Открытый ремень между разрешёнными валами сохраняет направление."
              : task.game === "lab"
                ? "Открывай исследования, сравнивай признаки и исключай несовместимые образцы. Выбери образец и доказательства, которые однозначно подтверждают вывод."
                : task.game === "delivery"
                  ? "Выбери партию, размести её на площадке и построй маршрут от входа по соседним клеткам склада. Резерв недоступен."
                  : "Выбери один ответ в каждом вопросе. Перед завершением можно изменить выбор."}
        </p>
        <p>
          Касание или Tab и Enter. Баллы за уровень начисляются один раз; время
          не влияет на результат.
        </p>
      </details>
    </section>
  );
}

function Signal({ task, draft, change, submit, busy }: EditorProps) {
  const p = task.puzzle as SignalPuzzle,
    rules = draft.rules as Rule[];
  const [showRules, setShowRules] = useState(false);
  const [trace, setTrace] = useState<ReturnType<typeof runSignal> | null>(null),
    [step, setStep] = useState(0),
    [running, setRunning] = useState(false);
  useEffect(() => {
    setTrace(null);
    setRunning(false);
  }, [rules]);
  useEffect(() => {
    if (!running || !trace) return;
    const timer = setTimeout(() => {
      if (step < trace.length - 1) setStep(step + 1);
      else setRunning(false);
    }, 650);
    return () => clearTimeout(timer);
  }, [running, step, trace]);
  const update = (next: Rule[]) => change({ ...draft, rules: next });
  return (
    <>
      <SignalBoard
        task={task}
        step={step}
        output={trace?.[step]?.output}
        running={running}
      />
      <div className="game-intro-card v5-program-summary">
        <span className="game-eyebrow">ТВОЯ ПРОГРАММА</span>
        {rules.map((rule, i) => (
          <strong key={i}>
            {rule.condition === "always"
              ? "Иначе"
              : `Если ${conditions[rule.condition]?.toLowerCase() ?? rule.condition}`}{" "}
            → выход {rule.output === "left" ? "А" : "Б"}
          </strong>
        ))}
      </div>
      <button
        className="game-primary"
        disabled={busy || running}
        onClick={() => {
          setTrace(runSignal(p, rules));
          setStep(0);
          setRunning(true);
        }}
      >
        Пробный запуск
      </button>
      <button
        className="game-secondary"
        disabled={busy}
        aria-expanded={showRules}
        onClick={() => setShowRules(!showRules)}
      >
        {showRules ? "Свернуть редактор" : "Изменить правило →"}
      </button>
      {trace && (
        <p className="game-notice" role="status">
          Упаковка {step + 1} из {p.stream.length}:{" "}
          {trace[step].ruleIndex < 0
            ? "нет подходящего правила"
            : `правило ${trace[step].ruleIndex + 1} → ${trace[step].output === "left" ? "А" : "Б"}`}
        </p>
      )}
      {showRules && (
        <>
          <div className="game-intro-card">
            <span className="game-eyebrow">
              ТВОЯ ПРОГРАММА · ПЕРВОЕ СОВПАДЕНИЕ
            </span>
            <p>{task.description}</p>
            {rules.map((rule, i) => (
              <div
                key={i}
                className={`signal-rule ${trace?.[step]?.ruleIndex === i ? "firing" : ""}`}
              >
                <span>{i + 1}.</span>
                <label>
                  <span className="sr-only">Условие правила {i + 1}</span>
                  <select
                    value={rule.condition}
                    disabled={busy}
                    onChange={(e) =>
                      update(
                        rules.map((r, n) =>
                          n === i ? { ...r, condition: e.target.value } : r,
                        ),
                      )
                    }
                  >
                    {p.allowedConditions.map((c) => (
                      <option key={c} value={c}>
                        {conditions[c] ?? c}
                      </option>
                    ))}
                  </select>
                </label>
                <span>→</span>
                <label>
                  <span className="sr-only">Выход правила {i + 1}</span>
                  <select
                    value={rule.output}
                    disabled={busy}
                    onChange={(e) =>
                      update(
                        rules.map((r, n) =>
                          n === i ? { ...r, output: e.target.value } : r,
                        ),
                      )
                    }
                  >
                    {p.outputs.map((o) => (
                      <option key={o} value={o}>
                        {o === "left" ? "А · налево" : "Б · направо"}
                      </option>
                    ))}
                  </select>
                </label>
                <div className="game-inline-actions">
                  <button
                    aria-label={`Поднять правило ${i + 1}`}
                    disabled={busy || i === 0}
                    onClick={() => {
                      const next = [...rules];
                      [next[i - 1], next[i]] = [next[i], next[i - 1]];
                      update(next);
                    }}
                  >
                    ↑
                  </button>
                  <button
                    aria-label={`Удалить правило ${i + 1}`}
                    disabled={busy || rules.length === 1}
                    onClick={() => update(rules.filter((_, n) => n !== i))}
                  >
                    ×
                  </button>
                </div>
              </div>
            ))}
          </div>
          <button
            className="game-secondary"
            disabled={busy || rules.length >= p.maxRules}
            onClick={() =>
              update([...rules, { condition: "always", output: "right" }])
            }
          >
            + Добавить блок · {rules.length}/{p.maxRules}
          </button>
        </>
      )}
      {trace && !running && (
        <>
          <ul className="game-trace">
            {trace.map((t) => (
              <li key={t.index}>
                {t.correct ? "✓" : "×"} Упаковка {t.index + 1}:{" "}
                {t.output ? (t.output === "left" ? "А" : "Б") : "без маршрута"}
                {!t.correct &&
                  ` · нужен выход ${t.expected === "left" ? "А" : "Б"}`}
              </li>
            ))}
          </ul>
          <button
            className="game-primary"
            disabled={busy}
            onClick={() => submit({ rules })}
          >
            {busy ? "Проверяем…" : "Проверить программу"}
          </button>
        </>
      )}
    </>
  );
}
function Movement({ task, draft, change, submit, busy }: EditorProps) {
  const p = task.puzzle as MovementPuzzle,
    gears = draft.gears as Point[],
    belts = (draft.belts ?? []) as Belt[];
  const [running, setRunning] = useState(false),
    [tool, setTool] = useState<"gear" | "belt">("gear"),
    [beltStart, setBeltStart] = useState<Point | null>(null),
    [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Point | null>(() => {
    const center = { x: Math.floor(p.width / 2), y: p.source.y };
    return !same(center, p.source) && !same(center, p.target) ? center : null;
  });
  const network = movementNetwork(p, gears, belts),
    directions = network.directions,
    targetDirection = directions.get(`${p.target.x},${p.target.y}`),
    detached = gears.filter((g) => !directions.has(`${g.x},${g.y}`)).length;
  function toggle(point: Point) {
    setRunning(false);
    setNotice("");
    if (gears.some((g) => same(g, point)))
      change({
        ...draft,
        gears: gears.filter((g) => !same(g, point)),
        belts: belts.filter((b) => !same(b.from, point) && !same(b.to, point)),
      });
    else if (gears.length < p.maxGears)
      change({ ...draft, gears: [...gears, point] });
  }
  function addBelt(point: Point) {
    setRunning(false);
    if (!beltStart) {
      setBeltStart(point);
      setNotice("Теперь выбери второй вал для открытого ремня.");
      return;
    }
    if (same(beltStart, point)) {
      setBeltStart(null);
      setNotice("Первый вал снят с выбора.");
      return;
    }
    const matches = (b: Belt) =>
      (same(b.from, beltStart) && same(b.to, point)) ||
      (same(b.to, beltStart) && same(b.from, point));
    if (!p.beltLinks?.some(matches)) {
      setNotice(
        "Эти валы нельзя соединить ремнём в этом уровне. Выбери другой вал либо нажми первый для отмены.",
      );
      return;
    }
    if (belts.some(matches)) {
      setNotice("Этот ремень уже установлен. Снять его можно кнопкой на поле.");
      setBeltStart(null);
      return;
    }
    if (belts.length >= (p.maxBelts ?? 0)) {
      setNotice(
        "Все доступные ремни установлены. Сними лишний, чтобы изменить передачу.",
      );
      return;
    }
    change({ ...draft, belts: [...belts, { from: beltStart, to: point }] });
    setBeltStart(null);
    setNotice("Открытый ремень установлен: направление вращения сохраняется.");
  }
  return (
    <>
      <MovementBoard
        task={task}
        gears={gears}
        belts={belts}
        running={running}
        busy={busy}
        selected={tool === "gear" ? selected : null}
        beltMode={tool === "belt"}
        beltStart={beltStart}
        onShaft={addBelt}
        onSelect={(point) => {
          setSelected(point);
          setRunning(false);
        }}
        onToggle={toggle}
        onRemoveBelt={(index) => {
          change({ ...draft, belts: belts.filter((_, i) => i !== index) });
          setRunning(false);
        }}
      />
      <div className="v5-parts-tray">
        <button
          className={tool === "gear" ? "selected" : ""}
          type="button"
          aria-pressed={tool === "gear"}
          disabled={busy}
          onClick={() => {
            setTool("gear");
            setBeltStart(null);
            setNotice("");
          }}
        >
          <strong>◎</strong>
          <span>
            Шестерня · {gears.length}/{p.maxGears}
          </span>
        </button>
        <button
          className={tool === "belt" ? "selected" : ""}
          type="button"
          aria-pressed={tool === "belt"}
          disabled={busy || !p.maxBelts || !p.beltLinks?.length}
          onClick={() => {
            setTool("belt");
            setBeltStart(null);
            setNotice(
              "Выбери первый и второй вал. Открытый ремень сохраняет направление вращения.",
            );
          }}
        >
          <strong>∞</strong>
          <span>
            Ремень · {belts.length}/{p.maxBelts ?? 0}
          </span>
        </button>
      </div>
      {tool === "gear" ? (
        <button
          className="game-primary"
          disabled={
            busy ||
            !selected ||
            gears.length >= p.maxGears ||
            gears.some((g) => selected && same(g, selected))
          }
          onClick={() => {
            if (selected) toggle(selected);
          }}
        >
          Установить шестерню
        </button>
      ) : (
        <p className="game-intro-card">
          {beltStart
            ? `Первый вал: ${beltStart.x + 1}, ${beltStart.y + 1}. Выбери второй вал.`
            : "Нажми на два занятых вала на поле."}
        </p>
      )}
      <p className="v5-action-hint">
        {tool === "gear"
          ? selected
            ? `Выбран узел ${selected.x + 1}, ${selected.y + 1} · цель ${p.target.direction === 1 ? "↻" : "↺"}`
            : "Выбери деталь для свободного узла"
          : "Шестерня меняет направление · открытый ремень сохраняет"}
      </p>
      {notice && (
        <p className="game-notice" role="status">
          {notice}
        </p>
      )}
      <button
        className="game-secondary"
        disabled={busy || (!gears.length && !belts.length)}
        onClick={() => setRunning(true)}
      >
        Запустить механизм
      </button>
      {running && (
        <p role="status" className="game-notice">
          {network.blocked
            ? "Механизм заблокирован: проверь ремни и направления вращения."
            : targetDirection === undefined
              ? "Выход не вращается: между колёсами есть разрыв."
              : detached
                ? `Отдельно от механизма: ${detached}. Присоедини или убери лишние детали.`
                : targetDirection === p.target.direction
                  ? "Цепочка работает: направление на выходе совпало."
                  : "Выход вращается в другую сторону. Проверь число зацеплений и ремни."}
        </p>
      )}
      {running && (
        <button
          className="game-primary"
          disabled={busy}
          onClick={() => submit({ gears, belts })}
        >
          {busy ? "Проверяем…" : "Проверить конструкцию"}
        </button>
      )}
      <button
        className="game-link"
        disabled={busy || (!gears.length && !belts.length)}
        onClick={() => {
          change({ ...draft, gears: [], belts: [] });
          setRunning(false);
          setBeltStart(null);
        }}
      >
        Снять все детали
      </button>
    </>
  );
}

function Lab({ task, draft, change, submit, busy }: EditorProps) {
  const p = task.puzzle as LabPuzzle,
    revealed = draft.revealed as string[],
    evidence = draft.evidence as string[],
    excluded = draft.excluded as string[],
    sampleId = draft.sampleId as string;
  const toggle = (key: string, values: string[], id: string) =>
    change({
      ...draft,
      [key]: values.includes(id)
        ? values.filter((v) => v !== id)
        : [...values, id],
    });
  const candidates = p.samples.filter((s) =>
    revealed.every((id) => s.properties[id] === p.observations[id]),
  );
  const lastRevealed = p.tests.find((test) => test.id === revealed.at(-1));
  return (
    <>
      <LabBoard
        task={task}
        revealed={revealed}
        excluded={excluded}
        sampleId={sampleId}
        busy={busy}
        onSelect={(id) => change({ ...draft, sampleId: id })}
      />
      <div className="game-intro-card">
        <span className="game-eyebrow">
          ПРОВЕРКА{" "}
          {String(Math.min(revealed.length + 1, p.tests.length)).padStart(
            2,
            "0",
          )}{" "}
          / СВОЙСТВА
        </span>
        {lastRevealed && (
          <strong>
            {lastRevealed.label}: {p.observations[lastRevealed.id]}
          </strong>
        )}
        <p className={lastRevealed ? "v5-lab-next" : undefined}>
          {p.tests.find((t) => !revealed.includes(t.id))
            ? `Сравни образцы: следующее исследование — ${p.tests.find((t) => !revealed.includes(t.id))!.label.toLowerCase()}.`
            : `Открыты все свойства. Совместимы ${candidates.length} из ${p.samples.length} образцов.`}
        </p>
      </div>
      {p.tests.find((t) => !revealed.includes(t.id)) ? (
        <button
          className="game-primary"
          disabled={busy}
          onClick={() => {
            const test = p.tests.find((t) => !revealed.includes(t.id))!;
            change({
              ...draft,
              revealed: [...revealed, test.id],
              evidence: [...new Set([...evidence, test.id])],
            });
          }}
        >
          Исследовать: {p.tests.find((t) => !revealed.includes(t.id))!.label}
        </button>
      ) : (
        <button
          className="game-primary"
          disabled={busy || !sampleId || !evidence.length}
          onClick={() => submit({ sampleId, evidence })}
        >
          {busy ? "Проверяем…" : "Подтвердить вывод"}
        </button>
      )}
      <details className="v5-research-details">
        <summary>Открыть справочник свойств →</summary>
        <h2>Выбери исследование</h2>
        <div className="game-test-list">
          {p.tests.map((test) => (
            <button
              className="game-secondary"
              key={test.id}
              disabled={busy || revealed.includes(test.id)}
              onClick={() =>
                change({
                  ...draft,
                  revealed: [...revealed, test.id],
                  evidence: [...evidence, test.id],
                })
              }
            >
              {revealed.includes(test.id)
                ? "✓ " + test.label + " · " + p.observations[test.id]
                : "Исследовать: " + test.label}
            </button>
          ))}
        </div>
        <p className="game-hint">
          По открытым свойствам совместимы {candidates.length} из{" "}
          {p.samples.length} образцов.
        </p>
        <h2>Справочник образцов</h2>
        <div className="lab-samples">
          {p.samples.map((sample) => (
            <article
              key={sample.id}
              className={`${excluded.includes(sample.id) ? "excluded " : ""}${sampleId === sample.id ? "selected" : ""}`}
            >
              <strong>{sample.name}</strong>
              <dl>
                {p.tests.map((test) => (
                  <div
                    key={test.id}
                    className={
                      revealed.includes(test.id) &&
                      sample.properties[test.id] !== p.observations[test.id]
                        ? "mismatch"
                        : ""
                    }
                  >
                    <dt>{test.label}</dt>
                    <dd>{sample.properties[test.id]}</dd>
                  </div>
                ))}
              </dl>
              <div className="game-inline-actions">
                <button
                  disabled={busy || excluded.includes(sample.id)}
                  aria-pressed={sampleId === sample.id}
                  onClick={() => change({ ...draft, sampleId: sample.id })}
                >
                  {sampleId === sample.id ? "✓ Выбран" : "Это мой образец"}
                </button>
                <button
                  disabled={busy}
                  aria-pressed={excluded.includes(sample.id)}
                  onClick={() =>
                    change({
                      ...draft,
                      excluded: excluded.includes(sample.id)
                        ? excluded.filter((v) => v !== sample.id)
                        : [...excluded, sample.id],
                      sampleId: sampleId === sample.id ? "" : sampleId,
                    })
                  }
                >
                  {excluded.includes(sample.id) ? "Вернуть" : "Исключить"}
                </button>
              </div>
            </article>
          ))}
        </div>
        <fieldset className="game-evidence">
          <legend>Доказательства к выводу</legend>
          {revealed.length === 0 && <p>Сначала проведи исследование.</p>}
          {p.tests
            .filter((t) => revealed.includes(t.id))
            .map((test) => (
              <label key={test.id}>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={evidence.includes(test.id)}
                  onChange={() => toggle("evidence", evidence, test.id)}
                />
                {test.label}: {p.observations[test.id]}
              </label>
            ))}
        </fieldset>
        <button
          className="game-primary"
          disabled={busy || !sampleId || !evidence.length}
          onClick={() => submit({ sampleId, evidence })}
        >
          {busy ? "Проверяем…" : "Подтвердить вывод"}
        </button>
        <p className="game-hint">
          Образец должен однозначно определяться выбранными доказательствами.
        </p>
      </details>
    </>
  );
}
function Delivery({ task, draft, change, submit, busy }: EditorProps) {
  const p = task.puzzle as DeliveryPuzzle,
    placements = draft.placements as Placement[],
    route = draft.route as Point[];
  const [selected, setSelected] = useState(""),
    [expanded, setExpanded] = useState(false),
    [routeMode, setRouteMode] = useState(false),
    [rotated, setRotated] = useState(false),
    [notice, setNotice] = useState("");
  const batch = p.batches.find((b) => b.id === selected);
  const count = (product: string) =>
    placements.filter(
      (item) =>
        p.batches.find((b) => b.id === item.batchId)?.product === product,
    ).length;
  function place(point: Point) {
    if (!batch) return;
    const placement = { ...point, batchId: batch.id, rotated };
    const error = placementError(
      batch,
      placement,
      placements,
      p.batches,
      p.width,
      p.height,
    );
    if (error) {
      setNotice(error);
      return;
    }
    change({
      ...draft,
      placements: [
        ...placements.filter((item) => item.batchId !== batch.id),
        placement,
      ],
    });
    setNotice("Партия размещена. Выбери следующую или построй маршрут.");
  }
  return (
    <>
      <DeliveryBoard
        task={task}
        route={route}
        selected={selected}
        chosen={placements.map((p) => p.batchId)}
        busy={busy}
        onCell={(point, stockId) => {
          if (!routeMode && stockId) {
            const stock = p.batches.find((b) => b.id === stockId)!;
            if (stock.reserved) {
              setNotice("Эта партия зарезервирована.");
              return;
            }
            setSelected(stockId);
            setExpanded(true);
            setNotice("Выбери место партии на площадке ниже.");
            return;
          }
          if (routeMode) {
            if (route.length >= 100) {
              setNotice("Убери лишние шаги: максимум 99.");
              return;
            }
            const next = appendRoute(route, point);
            if (next) {
              change({ ...draft, route: next });
              setNotice("");
            } else
              setNotice(
                "Продолжай от текущей клетки по горизонтали или вертикали.",
              );
          }
        }}
      />
      <div className="game-intro-card">
        <span className="game-eyebrow">ТВОЙ ЗАКАЗ</span>
        {p.order.map((o) => (
          <strong key={o.product}>
            {products[o.product] ?? o.product}: {count(o.product)} /{" "}
            {o.quantity}
          </strong>
        ))}
      </div>
      <button
        className="game-primary"
        disabled={busy}
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? "Свернуть управление заказом" : "Выбрать партии и маршрут"}
      </button>
      <p className="v5-action-hint">Нажми на доступные точки хранения</p>
      {notice && (
        <p className="game-notice" role="status">
          {notice}
        </p>
      )}
      {expanded && (
        <>
          <h2>1. Выбери партии</h2>
          <div className="delivery-batches">
            {p.batches.map((b) => (
              <button
                key={b.id}
                disabled={busy || b.reserved}
                aria-pressed={selected === b.id}
                className={`game-batch ${selected === b.id ? "selected" : ""}`}
                onClick={() => {
                  setSelected(b.id);
                  setNotice("Нажми клетку площадки, чтобы поставить партию.");
                }}
              >
                <strong>
                  {b.id.toUpperCase()} · {products[b.product] ?? b.product}
                </strong>
                <span>
                  {b.cells.length} {b.cells.length === 1 ? "клетка" : "клетки"}{" "}
                  ·{" "}
                  {b.reserved
                    ? "Резерв"
                    : placements.some((item) => item.batchId === b.id)
                      ? "Размещена"
                      : "Доступна"}
                </span>
                <small>
                  Склад: {b.location.x + 1}, {b.location.y + 1}
                </small>
              </button>
            ))}
          </div>
          <h2>2. Размести на площадке</h2>
          <div className="game-inline-actions">
            <button
              disabled={busy || !batch}
              className="game-secondary"
              aria-pressed={rotated}
              onClick={() => setRotated(!rotated)}
            >
              ↻ Поворот: {rotated ? "90°" : "0°"}
            </button>
            <button
              disabled={
                busy || !placements.some((item) => item.batchId === selected)
              }
              className="game-secondary"
              onClick={() =>
                change({
                  ...draft,
                  placements: placements.filter(
                    (item) => item.batchId !== selected,
                  ),
                })
              }
            >
              Убрать партию
            </button>
          </div>
          <p className="game-hint">
            {batch
              ? `Выбрана партия ${batch.id.toUpperCase()} · ${rotated ? "повёрнута" : "без поворота"}`
              : "Выбери партию выше. Упаковки занимают несколько клеток."}
          </p>
          <div className="game-live-stage">
            <span className="game-stage-label">ПЛОЩАДКА / БЕЗ ПЕРЕСЕЧЕНИЙ</span>
            <div
              className="game-grid packing-grid"
              style={{ "--columns": p.width } as CSSProperties}
            >
              {Array.from({ length: p.width * p.height }, (_, i) => {
                const point = { x: i % p.width, y: Math.floor(i / p.width) },
                  occupied = placements.find((item) =>
                    footprint(
                      p.batches.find((b) => b.id === item.batchId)!,
                      item,
                    ).some((cell) => same(cell, point)),
                  );
                return (
                  <button
                    disabled={busy || !batch}
                    className={occupied ? "occupied" : ""}
                    key={i}
                    aria-label={`Поставить партию, столбец ${point.x + 1}, ряд ${point.y + 1}${occupied ? ", занято партией " + occupied.batchId : ""}`}
                    onClick={() => place(point)}
                  >
                    {occupied ? occupied.batchId.toUpperCase() : "·"}
                  </button>
                );
              })}
            </div>
          </div>
          <h2>3. Проложи маршрут</h2>
          <button
            className="game-secondary"
            disabled={busy}
            aria-pressed={routeMode}
            onClick={() => {
              setRouteMode(!routeMode);
              setNotice(
                routeMode
                  ? "Выбирай партии на карте склада."
                  : "Режим маршрута: нажимай соседние клетки на большой карте склада выше.",
              );
            }}
          >
            {routeMode
              ? "Вернуться к выбору партий"
              : "Строить маршрут на карте ↑"}
          </button>
          <p className="game-hint">
            От входа нажимай соседние клетки на карте склада выше. Посети каждую
            выбранную партию. Пройдено: {route.length - 1} шагов.
          </p>
          <div className="game-inline-actions">
            <button
              disabled={busy || route.length <= 1}
              className="game-secondary"
              onClick={() => change({ ...draft, route: route.slice(0, -1) })}
            >
              ↶ Убрать шаг
            </button>
            <button
              disabled={busy || route.length <= 1}
              className="game-secondary"
              onClick={() => change({ ...draft, route: [p.start] })}
            >
              Сначала
            </button>
          </div>
          <button
            className="game-primary"
            disabled={busy || !placements.length || route.length < 2}
            onClick={() => submit({ placements, route })}
          >
            {busy ? "Проверяем…" : "Отправить заказ"}
          </button>
        </>
      )}
    </>
  );
}
function History({ task, draft, change, submit, busy }: EditorProps) {
  const p = task.puzzle as HistoryPuzzle,
    answers = draft.answers as Record<string, string>,
    index = Math.min(
      Math.max(Number(draft.index) || 0, 0),
      p.questions.length - 1,
    ),
    question = p.questions[index],
    answered = p.questions.filter((q) => answers[q.id]).length;
  return (
    <>
      <div className="quiz-progress">
        <span>
          Вопрос {index + 1} из {p.questions.length}
        </span>
        <progress value={answered} max={p.questions.length} />
      </div>
      <div className="game-quiz-card">
        <span className="game-eyebrow">ОТКРЫВАЕМ ИСТОРИЮ</span>
        <h2>{question.text}</h2>
        <fieldset>
          <legend className="sr-only">Выбери один ответ</legend>
          {question.options.map((option) => (
            <label
              className={answers[question.id] === option.id ? "selected" : ""}
              key={option.id}
            >
              <input
                type="radio"
                name={question.id}
                value={option.id}
                checked={answers[question.id] === option.id}
                disabled={busy}
                onChange={() =>
                  change({
                    ...draft,
                    answers: { ...answers, [question.id]: option.id },
                  })
                }
              />
              {option.text}
            </label>
          ))}
        </fieldset>
      </div>
      <div className="game-inline-actions">
        <button
          className="game-secondary"
          disabled={busy || index === 0}
          onClick={() => change({ ...draft, index: index - 1 })}
        >
          ← Назад
        </button>
        {index < p.questions.length - 1 && (
          <button
            className="game-primary"
            disabled={busy || !answers[question.id]}
            onClick={() => change({ ...draft, index: index + 1 })}
          >
            Следующий вопрос →
          </button>
        )}
      </div>
      {index === p.questions.length - 1 && (
        <button
          className="game-primary"
          disabled={busy || answered < p.questions.length}
          onClick={() => submit({ answers })}
        >
          {busy ? "Проверяем…" : "Завершить тест"}
        </button>
      )}
      <details className="game-help">
        <summary>Источники фактов</summary>
        {[...new Set(p.questions.map((q) => q.source))]
          .filter((url) => /^https:\/\//.test(url))
          .map((url) => (
            <p key={url}>
              <a target="_blank" rel="noreferrer" href={url}>
                Официальная история «Очаково» ↗
              </a>
            </p>
          ))}
      </details>
    </>
  );
}
