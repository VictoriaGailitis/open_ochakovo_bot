import { useEffect, useRef, useState } from "react";
import { DraftConflictError, DraftSnapshotClock } from "../draftClock";
import type { CSSProperties } from "react";
import type {
  CompletionResult,
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
  gearDirections,
  placementError,
  runSignal,
  same,
} from "./mechanics";
import { referenceStages } from "./ReferenceStages";
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
      return { gears: [] };
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
  const [editing, setEditing] = useState(
    task.game === "history" || Boolean(saved),
  );
  const [busy, setBusy] = useState(false),
    [result, setResult] = useState<CompletionResult | null>(null),
    [error, setError] = useState(""),
    [saveState, setSaveState] = useState("");
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
  return (
    <section className="game-player" aria-label={task.title}>
      <button
        type="button"
        className="game-back"
        onClick={() => {
          void leave();
        }}
        disabled={busy}
      >
        ← Задания
      </button>
      <p className="game-eyebrow">
        {initials[task.game]} {task.game !== "history" && "/ 05"} · УРОВЕНЬ{" "}
        {String(task.level).padStart(2, "0")} · +{task.points} БАЛЛОВ
      </p>
      <h1>{task.title}</h1>
      <p className="game-description">{task.description}</p>
      {!editing && task.game !== "history" && (
        <>
          <div
            className="game-reference-stage"
            aria-label="Иллюстрация игровой механики"
          >
            <div className="game-reference-inner">
              {referenceStages[task.game]}
            </div>
          </div>
          <div className="game-intro-card">
            <span className="game-eyebrow">
              {task.game === "signal"
                ? "ТВОЯ ПРОГРАММА"
                : task.game === "movement"
                  ? "ДЕТАЛИ ПЕРЕДАЧИ"
                  : task.game === "lab"
                    ? "ПРОВЕРКА 01 / СВОЙСТВА"
                    : "ТВОЙ ЗАКАЗ"}
            </span>
            <strong>
              {task.game === "signal"
                ? "Датчик → условие → действие"
                : task.game === "movement"
                  ? "◎ Шестерня → вращение"
                  : task.game === "lab"
                    ? "Сравни результаты и собери доказательства"
                    : (task.puzzle as DeliveryPuzzle).order
                        .map(
                          (o) =>
                            `${products[o.product] ?? o.product} × ${o.quantity}`,
                        )
                        .join(" · ")}
            </strong>
          </div>
          <button className="game-primary" onClick={() => setEditing(true)}>
            {task.game === "signal"
              ? "Собрать правило"
              : task.game === "movement"
                ? "Установить шестерню"
                : task.game === "lab"
                  ? "Исследовать образец"
                  : "Выбрать партии и маршрут"}
          </button>
          <p className="game-hint">
            {task.game === "signal"
              ? "Программа проверяется на пробном потоке"
              : task.game === "movement"
                ? "Выбери свободный узел и добавь передачу"
                : task.game === "lab"
                  ? "Условные образцы · учебная модель"
                  : "Нажми на доступные точки хранения"}
          </p>
        </>
      )}
      {editing && !result?.correct && (
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
      )}
      {error && (
        <p role="alert" className="game-error">
          {error}
        </p>
      )}
      {result && (
        <div
          className={`game-result ${result.correct ? "game-success" : "game-error"}`}
          role="status"
        >
          <h2>{result.correct ? "Дело сделано!" : "Пока не сходится"}</h2>
          {result.correct && (
            <strong>
              {result.alreadyCompleted
                ? "Тренировка завершена · баллы уже начислены"
                : `+${result.pointsAwarded} баллов`}
            </strong>
          )}
          {(result.errors ?? []).map((e, i) => (
            <p key={i}>{e}</p>
          ))}
          <p>{result.explanation || task.explanation}</p>
          {result.correct && (
            <>
              <button
                className="game-primary"
                onClick={() => onCareer(task.direction)}
              >
                Профессии по этому направлению →
              </button>
              <button
                className="game-secondary"
                onClick={() => {
                  setResult(null);
                  setEditing(true);
                }}
              >
                Потренироваться ещё
              </button>
              <button className="game-link" onClick={onExit}>
                К заданиям
              </button>
            </>
          )}
        </div>
      )}
      {editing && !result?.correct && (
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
        <summary>Как играть</summary>
        <p>
          {task.game === "signal"
            ? "Добавляй и переставляй правила. Для каждой упаковки срабатывает первое подходящее условие. Запусти поток и посмотри, где маршрут отличается от цели."
            : task.game === "movement"
              ? "Нажми на клетку, чтобы поставить или снять шестерню. Привод и выход закреплены. Соседние колёса меняют направление вращения. Соедини цепочку и запусти её."
              : task.game === "lab"
                ? "Открой исследования, сравни свойства со справочником и исключай несовместимые образцы. Выбери образец и отметь результаты, которые однозначно доказывают твой вывод."
                : task.game === "delivery"
                  ? "Выбери доступную партию, при необходимости поверни и нажми на клетку площадки. Собери точный заказ. На карте склада построй путь по соседним клеткам ко всем выбранным партиям."
                  : "Выбери один ответ в каждом вопросе. Можно вернуться и изменить выбор. После проверки появятся объяснения и источники."}
        </p>
        <p>
          Управление: касание или Tab и Enter. Баллы начисляются один раз за
          уровень; время не влияет на результат.
        </p>
      </details>
      {task.demo && (
        <small className="game-disclaimer">
          Учебная модель · знакомство с профессией
        </small>
      )}
    </section>
  );
}

function Signal({ task, draft, change, submit, busy }: EditorProps) {
  const p = task.puzzle as SignalPuzzle,
    rules = draft.rules as Rule[];
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
      <div className="game-live-stage">
        <span className="game-stage-label">
          ПОЛЕ АВТОМАТИЗАЦИИ / ПРОБНЫЙ ПОТОК
        </span>
        <div className="signal-stream">
          {p.stream.map((item, i) => (
            <div
              key={i}
              className={`signal-item ${item.color} ${trace && i === step ? "active" : ""}`}
            >
              <span>{item.marked ? "●" : "○"}</span>
              <small>{i + 1}</small>
            </div>
          ))}
        </div>
        <div className="signal-outputs">
          <span>↙ А · налево</span>
          <span>Б · направо ↘</span>
        </div>
        {trace && (
          <p aria-live="polite">
            Упаковка {step + 1}:{" "}
            {trace[step].ruleIndex < 0
              ? "Нет подходящего правила"
              : `правило ${trace[step].ruleIndex + 1} → ${trace[step].output === "left" ? "А" : "Б"}`}{" "}
            {trace[step].correct ? "✓" : "· неверный выход"}
          </p>
        )}
      </div>
      <div className="game-intro-card">
        <span className="game-eyebrow">ТВОЯ ПРОГРАММА · ПЕРВОЕ СОВПАДЕНИЕ</span>
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
    [running, setRunning] = useState(false);
  const directions = gearDirections(p, gears),
    targetDirection = directions.get(`${p.target.x},${p.target.y}`),
    detached = gears.filter((g) => !directions.has(`${g.x},${g.y}`)).length;
  return (
    <>
      <div className="game-live-stage">
        <span className="game-stage-label">МЕХАНИКА / ПЕРЕДАЧА ВРАЩЕНИЯ</span>
        <div
          className="game-grid gear-grid"
          style={{ "--columns": p.width } as CSSProperties}
        >
          {Array.from({ length: p.width * p.height }, (_, i) => {
            const point = { x: i % p.width, y: Math.floor(i / p.width) },
              source = same(point, p.source),
              target = same(point, p.target),
              placed = gears.some((g) => same(g, point)),
              direction = directions.get(`${point.x},${point.y}`);
            return (
              <button
                key={i}
                disabled={busy || source || target}
                className={`${source ? "gear-source " : ""}${target ? "gear-target " : ""}${placed ? "filled " : ""}`}
                aria-label={`${source ? "Привод" : target ? "Выход" : placed ? "Снять шестерню" : "Поставить шестерню"}, столбец ${point.x + 1}, ряд ${point.y + 1}`}
                aria-pressed={placed}
                onClick={() => {
                  setRunning(false);
                  if (placed)
                    change({
                      ...draft,
                      gears: gears.filter((g) => !same(g, point)),
                    });
                  else if (gears.length < p.maxGears)
                    change({ ...draft, gears: [...gears, point] });
                }}
              >
                <span
                  className={`gear-symbol ${running && direction ? "spinning" : ""}`}
                  style={{
                    animationDirection: direction === -1 ? "reverse" : "normal",
                  }}
                >
                  {source || target || placed ? "⚙" : "+"}
                </span>
                {source && <small>ПРИВОД</small>}
                {target && <small>ВЫХОД</small>}
                {running && direction && (
                  <small>{direction === 1 ? "↻" : "↺"}</small>
                )}
              </button>
            );
          })}
        </div>
        <p>
          Привод {p.source.direction === 1 ? "↻" : "↺"} · цель{" "}
          {p.target.direction === 1 ? "↻" : "↺"}
        </p>
      </div>
      <div className="game-intro-card">
        <strong>
          ◎ Шестерни · {gears.length}/{p.maxGears}
        </strong>
        <span>
          Нажми на свободную клетку, чтобы добавить деталь. Повторное нажатие
          убирает её.
        </span>
      </div>
      <button
        className="game-primary"
        disabled={busy}
        onClick={() => setRunning(true)}
      >
        Запустить механизм
      </button>
      {running && (
        <p role="status" className="game-notice">
          {targetDirection === undefined
            ? "Выход не вращается: между колёсами есть разрыв."
            : detached
              ? `Отдельно от механизма: ${detached}. Присоедини или убери лишние шестерни.`
              : targetDirection === p.target.direction
                ? "Цепочка работает: направление на выходе совпало."
                : "Выход вращается в другую сторону. Проверь число зацеплений."}
        </p>
      )}
      <button
        className="game-secondary"
        disabled={busy || !gears.length}
        onClick={() => {
          change({ ...draft, gears: [] });
          setRunning(false);
        }}
      >
        Снять все детали
      </button>
      <button
        className="game-primary"
        disabled={busy || !running}
        onClick={() => submit({ gears })}
      >
        {busy ? "Проверяем…" : "Проверить конструкцию"}
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
  return (
    <>
      <div className="game-live-stage lab-stage">
        <span className="game-stage-label">
          УЧЕБНЫЕ ОБРАЗЦЫ / ПОИСК НЕИЗВЕСТНОГО
        </span>
        <div className="lab-vial" aria-hidden="true">
          X
        </div>
        <div className="lab-observations">
          {p.tests.map((test) => (
            <div key={test.id}>
              {test.label}:{" "}
              <strong>
                {revealed.includes(test.id) ? p.observations[test.id] : "?"}
              </strong>
            </div>
          ))}
        </div>
      </div>
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
    </>
  );
}
function Delivery({ task, draft, change, submit, busy }: EditorProps) {
  const p = task.puzzle as DeliveryPuzzle,
    placements = draft.placements as Placement[],
    route = draft.route as Point[];
  const [selected, setSelected] = useState(""),
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
      <div className="game-intro-card">
        <span className="game-eyebrow">ТВОЙ ЗАКАЗ</span>
        {p.order.map((o) => (
          <strong key={o.product}>
            {products[o.product] ?? o.product}: {count(o.product)} /{" "}
            {o.quantity}
          </strong>
        ))}
      </div>
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
              {b.cells.length} {b.cells.length === 1 ? "клетка" : "клетки"} ·{" "}
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
      <p className="game-hint">
        От входа нажимай соседние клетки по горизонтали или вертикали. Посети
        каждую выбранную партию. На карте видны все точки хранения.
      </p>
      <div className="game-live-stage">
        <span className="game-stage-label">СКЛАД / ДОСТУПНОСТЬ И МАРШРУТ</span>
        <div
          className="game-grid warehouse-grid"
          style={{ "--columns": p.warehouse.width } as CSSProperties}
        >
          {Array.from(
            { length: p.warehouse.width * p.warehouse.height },
            (_, i) => {
              const point = {
                  x: i % p.warehouse.width,
                  y: Math.floor(i / p.warehouse.width),
                },
                stock = p.batches.find((b) => same(b.location, point)),
                onRoute = route.some((r) => same(r, point)),
                last = same(route.at(-1)!, point),
                start = same(p.start, point),
                chosen =
                  stock && placements.some((item) => item.batchId === stock.id);
              return (
                <button
                  disabled={busy}
                  key={i}
                  className={`${onRoute ? "on-route " : ""}${last ? "current " : ""}${stock?.reserved ? "reserved " : ""}${chosen ? "chosen" : ""}`}
                  aria-label={`Маршрут, столбец ${point.x + 1}, ряд ${point.y + 1}${stock ? ", партия " + stock.id : ""}`}
                  onClick={() => {
                    if (route.length >= 100) {
                      setNotice(
                        "Маршрут ограничен 99 шагами. Убери лишние шаги или начни сначала.",
                      );
                      return;
                    }
                    const next = appendRoute(route, point);
                    if (!next) {
                      setNotice(
                        "Продолжай от текущей клетки: один шаг по горизонтали или вертикали.",
                      );
                      return;
                    }
                    change({ ...draft, route: next });
                    setNotice("");
                  }}
                >
                  {start
                    ? "ВХОД"
                    : stock
                      ? stock.id.toUpperCase()
                      : onRoute
                        ? "•"
                        : "·"}
                  {last && <small>Ты здесь</small>}
                </button>
              );
            },
          )}
        </div>
        <p>
          {route.length - 1} шагов · посещено{" "}
          {
            placements.filter((item) =>
              route.some((r) =>
                same(r, p.batches.find((b) => b.id === item.batchId)!.location),
              ),
            ).length
          }
          /{placements.length} точек
        </p>
      </div>
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
      {notice && (
        <p className="game-notice" role="status">
          {notice}
        </p>
      )}
      <button
        className="game-primary"
        disabled={busy || !placements.length || route.length < 2}
        onClick={() => submit({ placements, route })}
      >
        {busy ? "Проверяем…" : "Отправить заказ"}
      </button>
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
