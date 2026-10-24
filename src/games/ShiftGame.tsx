import { useEffect, useRef, useState } from "react";
import { DraftConflictError, DraftSnapshotClock } from "../draftClock";
import type {
  ShiftCheck,
  ShiftCompletionResult,
  ShiftDraft,
  ShiftGameProps,
  ShiftMetric,
  ShiftOption,
  ShiftPuzzle,
  ShiftView,
} from "./ShiftTypes";
import {
  MAX_SHIFT_OBSERVATIONS,
  normalizeShiftDraft,
  pinShiftFact,
  removeShiftObservation,
  shiftConclusionReady,
  shiftPlotGeometry,
  updateShiftNote,
} from "./shiftMechanics";
import "./shift.css";

const shortLabels: Record<string, string> = {
  output: "Выпуск",
  feed: "Подача",
  capping: "Укупорка",
  packaging: "Упаковка",
  queue: "Очередь",
  signals: "Сигналы",
  samples: "Проверка проб",
  rejects: "Отбраковка",
  pressure: "Воздух",
  temperature: "Температура",
  boxes: "Коробки",
  target: "Задание",
};
const titles: Record<ShiftView, string> = {
  overview: "Что изменилось на линии?",
  metric: "Показатель — подробнее",
  scheme: "Где меняется поток?",
  journal: "События смены",
  event: "Детали события",
  checks: "Результаты проверок",
  check: "Результат проверки",
  observations: "Мои наблюдения",
  conclusion: "Собери своё объяснение",
  criteria: "Разбор с командой",
};
const tabs: { view: ShiftView; label: string }[] = [
  { view: "overview", label: "Обзор" },
  { view: "scheme", label: "Схема" },
  { view: "journal", label: "Журнал" },
  { view: "checks", label: "Проверки" },
];
const decimalIds = new Set(["rejects", "pressure", "temperature"]);
function number(value: number, decimal = false) {
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: decimal ? 1 : 0,
    maximumFractionDigits: 2,
  }).format(value);
}
function metricValue(
  metric: ShiftMetric,
  value = metric.value,
  compact = false,
) {
  const formatted = number(value, decimalIds.has(metric.id));
  if (metric.id === "samples") return `${formatted} / 40`;
  if (["queue", "boxes", "target"].includes(metric.id))
    return compact ? formatted : `${formatted} ${metric.unit}`;
  if (["output", "feed", "capping", "packaging", "signals"].includes(metric.id))
    return `${formatted} / мин`;
  return `${formatted} ${metric.unit}`;
}
const errorMessage = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Не удалось сохранить данные. Повтори действие.";

export function ShiftGame(props: ShiftGameProps) {
  return <ShiftSession key={props.task.id} {...props} />;
}
export default ShiftGame;
function ShiftSession({
  task,
  draft: saved,
  draftRevision = 0,
  onSave,
  onComplete,
  onCareer,
  onExit,
}: ShiftGameProps) {
  const puzzle = task.puzzle;
  const [draft, setDraft] = useState<ShiftDraft>(() =>
    normalizeShiftDraft(saved, puzzle),
  );
  const [busy, setBusy] = useState(false),
    [result, setResult] = useState<ShiftCompletionResult | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [saveStatus, setSaveStatus] = useState("");
  const saveRef = useRef(onSave),
    latest = useRef(draft),
    queue = useRef(Promise.resolve()),
    mounted = useRef(true),
    shouldSave = useRef(true),
    saveGeneration = useRef(0),
    heading = useRef<HTMLHeadingElement>(null),
    composer = useRef<HTMLDivElement>(null);
  const snapshotClock = useRef<DraftSnapshotClock<ShiftDraft> | null>(null);
  if (!snapshotClock.current)
    snapshotClock.current = new DraftSnapshotClock(draft, draftRevision);
  saveRef.current = onSave;
  latest.current = draft;
  shouldSave.current = !result?.correct;
  function persist(value: ShiftDraft) {
    const revision = snapshotClock.current!.revisionOf(value);
    const operation = queue.current
      .catch(() => undefined)
      .then(() => saveRef.current(value, revision))
      .catch((failure: unknown) => {
        if (failure instanceof DraftConflictError && mounted.current) {
          if (latest.current === value) {
            const current = normalizeShiftDraft(failure.draft, puzzle);
            snapshotClock.current!.restore(current, failure.revision);
            latest.current = current;
            setDraft(current);
            setResult(null);
            setNotice(
              "Черновик изменён в другой вкладке. Загружена актуальная версия сервера; проверь данные.",
            );
          } else {
            setNotice(
              "Черновик изменён в другой вкладке. Твоя последняя правка сохранена в редакторе; проверь данные перед отправкой.",
            );
          }
        }
        throw failure;
      });
    queue.current = operation;
    return operation;
  }
  useEffect(() => {
    mounted.current = true;
    const savePage = () => {
      if (shouldSave.current)
        void saveRef
          .current(
            latest.current,
            snapshotClock.current!.revisionOf(latest.current),
          )
          .catch(() => undefined);
    };
    window.addEventListener("pagehide", savePage);
    return () => {
      window.removeEventListener("pagehide", savePage);
      mounted.current = false;
      if (shouldSave.current)
        void persist(latest.current).catch(() => undefined);
    };
  }, []);
  useEffect(() => {
    if (result?.correct) return;
    const generation = ++saveGeneration.current;
    setSaveStatus("Сохраняем…");
    const timer = setTimeout(() => {
      void persist(draft)
        .then(() => {
          if (mounted.current && generation === saveGeneration.current)
            setSaveStatus("Прогресс сохранён");
        })
        .catch(() => {
          if (mounted.current && generation === saveGeneration.current)
            setSaveStatus("Не сохранено — повторить");
        });
    }, 650);
    return () => clearTimeout(timer);
  }, [draft, result?.correct]);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView({ block: "start" });
  }, [draft.view, result?.correct]);
  useEffect(() => {
    if (draft.composingFactId)
      composer.current?.scrollIntoView({ block: "center" });
  }, [draft.composingFactId]);
  const change = (next: ShiftDraft) => {
    snapshotClock.current!.edit(next);
    latest.current = next;
    setDraft(next);
    setError("");
    setNotice("");
    if (result && !result.correct) setResult(null);
  };
  const navigate = (view: ShiftView) =>
    change({
      ...draft,
      view,
      composingFactId: "",
      composingNote: "",
      editingFactId: "",
    });
  function openMetric(id: string) {
    change({
      ...draft,
      view: "metric",
      metricId: id,
      composingFactId: "",
      composingNote: "",
    });
  }
  async function leave() {
    if (busy) return;
    setBusy(true);
    try {
      if (!result?.correct) await persist(latest.current);
      onExit();
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }
  async function submit() {
    if (busy || !shiftConclusionReady(draft)) return;
    setBusy(true);
    setError("");
    try {
      await persist(latest.current);
      const completion = await onComplete({ ...latest.current.conclusion });
      if (mounted.current) {
        setResult(completion as ShiftCompletionResult);
        if (!completion.correct)
          setError(
            completion.errors?.join(" ") ||
              "Сопоставь вывод с выбранными основаниями.",
          );
      }
    } catch (e) {
      if (mounted.current) setError(errorMessage(e));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  function pin(factId: string, note = "") {
    const fact = puzzle.facts.find((f) => f.id === factId);
    if (!fact) return;
    if (draft.observations.some((o) => o.factId === factId)) {
      setNotice(
        "Это наблюдение уже закреплено. Заметку можно изменить в «Моих наблюдениях».",
      );
      return;
    }
    if (draft.observations.length >= MAX_SHIFT_OBSERVATIONS) {
      setError(
        "Список заполнен. Убери лишнее наблюдение, чтобы закрепить новое.",
      );
      return;
    }
    change(pinShiftFact(draft, fact, note));
    setNotice("Наблюдение закреплено.");
  }
  function startNote(factId: string) {
    change({ ...draft, composingFactId: factId, composingNote: "" });
  }
  const metric =
    puzzle.metrics.find((m) => m.id === draft.metricId) ?? puzzle.metrics[0];
  const event =
    puzzle.journal.find((e) => e.id === draft.eventId) ?? puzzle.journal[0];
  const check =
    puzzle.checks.find((c) => c.id === draft.checkId) ?? puzzle.checks[0];
  const selectedScheme = [...puzzle.scheme.nodes, ...puzzle.scheme.flows].find(
    (n) => n.id === draft.schemeId,
  );
  const schemeFact = puzzle.facts.find(
    (f) => f.id === (selectedScheme?.factId ?? puzzle.scheme.flows[0]?.factId),
  );
  const detailTitle =
    draft.view === "metric" && metric
      ? `${shortLabels[metric.id] ?? metric.label} — подробнее`
      : draft.view === "check" && check
        ? check.title
        : titles[draft.view];
  const showTabs =
    ["overview", "metric", "scheme", "journal", "checks", "check"].includes(
      draft.view,
    ) && !result?.correct;
  const activeTab =
    draft.view === "metric"
      ? "overview"
      : draft.view === "check"
        ? "checks"
        : draft.view;
  const factsById = new Map(puzzle.facts.map((f) => [f.id, f]));
  const pinned = (id: string) =>
    draft.observations.some((o) => o.factId === id);
  const pinControl = (factId: string, label = "Закрепить наблюдение") => {
    const fact = factsById.get(factId);
    if (!fact) return null;
    return (
      <div className="shift-pin-controls">
        <button
          className="shift-primary"
          disabled={busy || pinned(factId)}
          onClick={() => pin(factId)}
        >
          {pinned(factId) ? "Наблюдение закреплено" : label}
        </button>
        {!pinned(factId) && (
          <button
            className="shift-link"
            disabled={busy}
            onClick={() => startNote(factId)}
          >
            Добавить свою заметку →
          </button>
        )}
      </div>
    );
  };
  return (
    <section
      className="shift-game"
      aria-label="Разберись в смене"
      aria-busy={busy}
    >
      <div className="shift-caption-row">
        <p className="shift-caption">
          РАЗБЕРИСЬ В СМЕНЕ / {puzzle.snapshotTime}
        </p>
        <button
          className="shift-exit"
          disabled={busy}
          onClick={() => {
            void leave();
          }}
        >
          ← Задания
        </button>
      </div>
      <h1 ref={heading} tabIndex={-1}>
        {result?.correct ? "Разбор с командой" : detailTitle}
      </h1>
      {showTabs && (
        <nav className="shift-tabs" aria-label="Материалы смены">
          {tabs.map((tab) => (
            <button
              key={tab.view}
              className={activeTab === tab.view ? "active" : ""}
              aria-current={activeTab === tab.view ? "page" : undefined}
              disabled={busy}
              onClick={() => navigate(tab.view)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      )}
      {result?.correct ? (
        <ShiftResult
          result={result}
          onCareer={() => onCareer(task.direction)}
          onReview={() => {
            setResult(null);
            navigate("conclusion");
          }}
          onExit={onExit}
        />
      ) : (
        <>
          {draft.view === "overview" && (
            <>
              <p className="shift-label shift-muted">
                Найди значимые данные и собери объяснение. Единицы и сравнение —
                на карточках.
              </p>
              <div className="shift-metric-grid">
                {puzzle.metrics.map((item) => (
                  <button
                    className="shift-metric-card"
                    key={item.id}
                    onClick={() => openMetric(item.id)}
                    disabled={busy}
                    aria-label={`${shortLabels[item.id] ?? item.label}: ${metricValue(item)}; ранее ${metricValue(item, item.previous)}`}
                  >
                    <span>{shortLabels[item.id] ?? item.label}</span>
                    <strong>{metricValue(item, item.value, true)}</strong>
                    <small>
                      ранее{" "}
                      {["samples", "rejects"].includes(item.id)
                        ? metricValue(item, item.previous, true)
                        : number(item.previous, decimalIds.has(item.id))}
                    </small>
                  </button>
                ))}
              </div>
              <button
                className="shift-primary"
                onClick={() => navigate("observations")}
              >
                Мои наблюдения
                {draft.observations.length
                  ? ` · ${draft.observations.length}`
                  : ""}
              </button>
              <p className="shift-small shift-muted">
                Открой любой показатель для подробностей. Данные учебные.
              </p>
              <details className="shift-hypothesis">
                <summary>Моё предположение</summary>
                <label className="shift-label">
                  Что ты хочешь проверить?
                  <textarea
                    value={draft.hypothesis}
                    maxLength={2000}
                    disabled={busy}
                    placeholder="Запиши гипотезу своими словами"
                    onChange={(e) =>
                      change({ ...draft, hypothesis: e.target.value })
                    }
                  />
                </label>
                <p className="shift-small shift-muted">
                  Это рабочая заметка. Её текст не оценивается.
                </p>
              </details>
            </>
          )}
          {draft.view === "metric" && metric && (
            <>
              <div className="shift-number-cards">
                <article className="shift-card">
                  <p className="shift-caption">СЕЙЧАС</p>
                  <h2>{metricValue(metric)}</h2>
                  <p className="shift-muted">Снимок {metric.time}</p>
                </article>
                <article className="shift-card">
                  <p className="shift-caption">СРАВНЕНИЕ</p>
                  <h2>
                    {metric.id === "samples"
                      ? metricValue(metric, metric.previous, true)
                      : number(metric.previous, decimalIds.has(metric.id))}
                  </h2>
                  <p className="shift-muted">Предыдущий снимок</p>
                </article>
              </div>
              <ShiftPlot metric={metric} />
              <p className="shift-body shift-muted">
                {factsById.get(metric.factId)?.text}
              </p>
              {pinControl(metric.factId)}
              {metric.historyFactId && (
                <button
                  className="shift-secondary"
                  disabled={busy || pinned(metric.historyFactId)}
                  onClick={() => pin(metric.historyFactId!)}
                >
                  {pinned(metric.historyFactId)
                    ? "Динамика закреплена"
                    : "Закрепить динамику графика"}
                </button>
              )}
              <button
                className="shift-link"
                onClick={() => navigate("observations")}
              >
                Мои наблюдения →
              </button>
              <p className="shift-small shift-muted">
                {metric.unit} · учебная модель. Открытие карточки не начисляет
                баллы.
              </p>
              <details className="shift-data-table">
                <summary>Точные значения и время</summary>
                <table>
                  <caption>
                    {metric.label} · {metric.unit}
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Время снимка</th>
                      <th scope="col">Значение</th>
                    </tr>
                  </thead>
                  <tbody>
                    {metric.series.map((point, i) => (
                      <tr key={`${point.time}-${i}`}>
                        <th scope="row">{point.time}</th>
                        <td>
                          {number(point.value, decimalIds.has(metric.id))}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="shift-small shift-muted">
                  {puzzle.measurementWindow}
                </p>
              </details>
            </>
          )}
          {draft.view === "scheme" && (
            <>
              <p className="shift-label shift-muted">
                Изучи участки и движение между ними. Схема показывает текущий
                снимок.
              </p>
              <ShiftScheme
                puzzle={puzzle}
                selectedId={draft.schemeId}
                onSelect={(id) =>
                  change({
                    ...draft,
                    schemeId: id,
                    composingFactId: "",
                    composingNote: "",
                  })
                }
              />
              {schemeFact && (
                <>
                  <article className="shift-card">
                    <p className="shift-caption">НАБЛЮДЕНИЕ УЧАСТКА</p>
                    <h2>
                      {selectedScheme &&
                      "label" in selectedScheme &&
                      selectedScheme.label.length < 70
                        ? selectedScheme.label
                        : "Наблюдение потока"}
                    </h2>
                    <p className="shift-muted">{schemeFact.text}</p>
                  </article>
                  {pinControl(schemeFact.id)}
                </>
              )}
              <button
                className="shift-link"
                onClick={() => navigate("observations")}
              >
                Открыть мои наблюдения →
              </button>
            </>
          )}
          {draft.view === "journal" && (
            <>
              <p className="shift-label shift-muted">
                Сопоставь время событий с изменением показателей.
              </p>
              <div className="shift-journal">
                {puzzle.journal.map((item) => (
                  <button
                    key={item.id}
                    className="shift-journal-event"
                    disabled={busy}
                    onClick={() =>
                      change({
                        ...draft,
                        view: "event",
                        eventId: item.id,
                        composingFactId: "",
                        composingNote: "",
                      })
                    }
                  >
                    <time>{item.time.replace(/:00$/, "")}</time>
                    <span>{item.title}</span>
                    <span aria-hidden="true" className="shift-row-arrow">
                      →
                    </span>
                  </button>
                ))}
              </div>
              <button
                className="shift-link"
                onClick={() => navigate("observations")}
              >
                Мои наблюдения →
              </button>
            </>
          )}
          {draft.view === "event" && event && (
            <>
              <p className="shift-caption">{event.time} / ЖУРНАЛ ИЗМЕНЕНИЙ</p>
              <article className="shift-card">
                <p className="shift-caption">СОБЫТИЕ СМЕНЫ</p>
                <h2>{event.title}</h2>
                <p className="shift-muted">{event.detail}</p>
              </article>
              <p className="shift-body shift-muted">
                Событие — один источник. Сопоставь его с графиком участка и
                наблюдением потока.
              </p>
              {pinControl(event.factId, "Закрепить событие")}
              <button
                className="shift-secondary"
                onClick={() => navigate("journal")}
              >
                Вернуться к журналу
              </button>
              <button
                className="shift-link"
                onClick={() => navigate("observations")}
              >
                Мои наблюдения →
              </button>
            </>
          )}
          {draft.view === "checks" && (
            <>
              <p className="shift-label shift-muted">
                Проверки помогают подтвердить или опровергнуть гипотезу.
              </p>
              {puzzle.checks.map((item) => (
                <div key={item.id} className="shift-check-block">
                  <article className="shift-card">
                    <p className="shift-caption">{item.title.toUpperCase()}</p>
                    <h2>{item.title}</h2>
                    <p className="shift-muted">{item.result}</p>
                    <button
                      className="shift-link"
                      disabled={busy}
                      onClick={() =>
                        change({
                          ...draft,
                          view: "check",
                          checkId: item.id,
                          composingFactId: "",
                          composingNote: "",
                        })
                      }
                    >
                      Рассмотреть проверку →
                    </button>
                  </article>
                  {pinControl(item.factId, "Закрепить результат")}
                </div>
              ))}
              <button
                className="shift-link"
                onClick={() => navigate("observations")}
              >
                Мои наблюдения →
              </button>
            </>
          )}
          {draft.view === "check" && check && (
            <>
              <ShiftCheckDetail check={check} />
              {pinControl(check.factId, "Закрепить результат")}
              <button
                className="shift-secondary"
                onClick={() => navigate("checks")}
              >
                К результатам проверок
              </button>
              <button
                className="shift-link"
                onClick={() => navigate("observations")}
              >
                Мои наблюдения →
              </button>
            </>
          )}
          {draft.view === "observations" && (
            <>
              <p className="shift-label shift-muted">
                Здесь появляются только закреплённые тобой сведения. Убирай
                лишнее и проверяй противоречия.
              </p>
              <div
                className={`shift-observations ${draft.observations.length ? "" : "empty"}`}
              >
                {draft.observations.map((observation) => (
                  <article
                    key={observation.factId}
                    className="shift-observation"
                  >
                    <div className="shift-observation-head">
                      <p className="shift-caption">
                        {observation.source} · {observation.time}
                      </p>
                      <button
                        className="shift-remove"
                        aria-label={`Убрать наблюдение: ${observation.source}`}
                        disabled={busy}
                        onClick={() =>
                          change(
                            removeShiftObservation(draft, observation.factId),
                          )
                        }
                      >
                        ×
                      </button>
                    </div>
                    <p>{observation.fact}</p>
                    {draft.editingFactId === observation.factId ? (
                      <>
                        <label className="shift-small">
                          Моя заметка
                          <textarea
                            maxLength={2000}
                            value={observation.note}
                            disabled={busy}
                            onChange={(e) =>
                              change(
                                updateShiftNote(
                                  draft,
                                  observation.factId,
                                  e.target.value,
                                ),
                              )
                            }
                          />
                        </label>
                        <button
                          className="shift-link"
                          onClick={() =>
                            change({ ...draft, editingFactId: "" })
                          }
                        >
                          Готово
                        </button>
                      </>
                    ) : (
                      <>
                        {observation.note && (
                          <p className="shift-player-note">
                            {observation.note}
                          </p>
                        )}
                        <button
                          className="shift-note-edit"
                          disabled={busy}
                          onClick={() =>
                            change({
                              ...draft,
                              editingFactId: observation.factId,
                            })
                          }
                        >
                          {observation.note
                            ? "Изменить заметку"
                            : "Добавить заметку"}
                        </button>
                      </>
                    )}
                  </article>
                ))}
              </div>
              <button
                className="shift-secondary"
                onClick={() => navigate("overview")}
              >
                Продолжить исследование
              </button>
              <button
                className="shift-primary"
                onClick={() => navigate("conclusion")}
              >
                Собрать вывод
              </button>
              <p className="shift-small shift-muted">
                Если список пуст, открой показатель, событие или проверку и
                нажми «Закрепить».
              </p>
            </>
          )}
          {draft.view === "conclusion" && (
            <>
              <ShiftSelect
                label="Что изменилось?"
                placeholder="Опиши наблюдаемое изменение"
                options={puzzle.conclusion.observedChange}
                value={draft.conclusion.observedChange}
                disabled={busy}
                onChange={(value) =>
                  change({
                    ...draft,
                    conclusion: { ...draft.conclusion, observedChange: value },
                  })
                }
              />
              <ShiftSelect
                label="Чем это объясняется?"
                placeholder="Сформулируй гипотезу"
                options={puzzle.conclusion.explanation}
                value={draft.conclusion.explanation}
                disabled={busy}
                onChange={(value) =>
                  change({
                    ...draft,
                    conclusion: { ...draft.conclusion, explanation: value },
                  })
                }
              />
              <fieldset className="shift-card shift-evidence">
                <legend className="shift-caption">ОСНОВАНИЯ</legend>
                <h2>Выбери свои наблюдения</h2>
                <p className="shift-muted">
                  Отметь источники, которые подтверждают вывод.
                </p>
                {draft.observations.length ? (
                  draft.observations.map((observation) => (
                    <label key={observation.factId}>
                      <input
                        type="checkbox"
                        disabled={busy}
                        checked={draft.conclusion.evidence.includes(
                          observation.factId,
                        )}
                        onChange={() =>
                          change({
                            ...draft,
                            conclusion: {
                              ...draft.conclusion,
                              evidence: draft.conclusion.evidence.includes(
                                observation.factId,
                              )
                                ? draft.conclusion.evidence.filter(
                                    (id) => id !== observation.factId,
                                  )
                                : [
                                    ...draft.conclusion.evidence,
                                    observation.factId,
                                  ],
                            },
                          })
                        }
                      />
                      <span>
                        <small>
                          {observation.source} · {observation.time}
                        </small>
                        {observation.fact}
                      </span>
                    </label>
                  ))
                ) : (
                  <button
                    className="shift-link"
                    onClick={() => navigate("overview")}
                  >
                    Вернуться к исследованию и закрепить данные →
                  </button>
                )}
              </fieldset>
              <ShiftSelect
                label="Следующий шаг и ответственный"
                placeholder="Что предложишь команде?"
                options={puzzle.conclusion.nextStep}
                value={draft.conclusion.nextStep}
                disabled={busy}
                onChange={(value) =>
                  change({
                    ...draft,
                    conclusion: { ...draft.conclusion, nextStep: value },
                  })
                }
              />
              <ShiftSelect
                label="Кому передать проверенные данные?"
                placeholder="Выбери ответственного"
                options={puzzle.conclusion.responsible}
                value={draft.conclusion.responsible}
                disabled={busy}
                onChange={(value) =>
                  change({
                    ...draft,
                    conclusion: { ...draft.conclusion, responsible: value },
                  })
                }
              />
              <button
                className="shift-primary"
                disabled={busy || !shiftConclusionReady(draft)}
                onClick={() => {
                  void submit();
                }}
              >
                {busy ? "Проверяем основания…" : "Проверить вывод"}
              </button>
              <button
                className="shift-secondary"
                onClick={() => navigate("criteria")}
              >
                Посмотреть критерии разбора
              </button>
              <button
                className="shift-link"
                onClick={() => navigate("observations")}
              >
                Вернуться к наблюдениям →
              </button>
              <p className="shift-small shift-muted">
                Свободные заметки не оцениваются. Проверяются утверждения
                конструктора и выбранные основания.
              </p>
            </>
          )}
          {draft.view === "criteria" && (
            <ShiftCriteria
              onBack={() => navigate("conclusion")}
              onCareer={() => onCareer(task.direction)}
            />
          )}
          {draft.composingFactId && factsById.get(draft.composingFactId) && (
            <div
              ref={composer}
              className="shift-note-composer"
              role="region"
              aria-label="Заметка к наблюдению"
            >
              <p className="shift-caption">СОХРАНИТЬ НАБЛЮДЕНИЕ</p>
              <p>{factsById.get(draft.composingFactId)?.text}</p>
              <label className="shift-label">
                Моя заметка
                <textarea
                  maxLength={2000}
                  value={draft.composingNote}
                  disabled={busy}
                  placeholder="Что ты хочешь сопоставить с этим фактом?"
                  onChange={(e) =>
                    change({ ...draft, composingNote: e.target.value })
                  }
                />
              </label>
              <button
                className="shift-primary"
                disabled={busy}
                onClick={() => pin(draft.composingFactId, draft.composingNote)}
              >
                Закрепить с заметкой
              </button>
              <button
                className="shift-link"
                onClick={() =>
                  change({ ...draft, composingFactId: "", composingNote: "" })
                }
              >
                Отмена
              </button>
            </div>
          )}
          {error && (
            <p className="shift-error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="shift-notice" role="status">
              {notice}
            </p>
          )}
          <div className="shift-tools">
            <details className="shift-inquiry">
              <summary>Нужен следующий вопрос?</summary>
              <p className="shift-label shift-muted">
                Подсказка направляет исследование и не влияет на баллы.
              </p>
              {draft.hintIndex >= 0 && (
                <p className="shift-inquiry-question" role="status">
                  {puzzle.hints[draft.hintIndex]}
                </p>
              )}
              <button
                className="shift-secondary"
                disabled={busy || !puzzle.hints.length}
                onClick={() =>
                  change({
                    ...draft,
                    hintIndex: (draft.hintIndex + 1) % puzzle.hints.length,
                  })
                }
              >
                Вопрос для исследования
              </button>
            </details>
            <button
              className="shift-save"
              aria-live="polite"
              disabled={busy}
              onClick={() => {
                setSaveStatus("Сохраняем…");
                void persist(latest.current)
                  .then(() => setSaveStatus("Прогресс сохранён"))
                  .catch((e) => {
                    setSaveStatus("Не сохранено — повторить");
                    setError(errorMessage(e));
                  });
              }}
            >
              {saveStatus || "Сохранить прогресс"}
            </button>
          </div>
        </>
      )}
      <details className="shift-model-note">
        <summary>Об учебной модели</summary>
        <p>{puzzle.modelNote}</p>
        <p>{puzzle.measurementWindow}</p>
        <p>
          За первое завершение варианта — до {task.points} баллов. За скорость и
          открытие материалов баллы не начисляются. Управление: касание, Tab и
          Enter.
        </p>
      </details>
    </section>
  );
}

function ShiftSelect({
  label,
  placeholder,
  options,
  value,
  onChange,
  disabled,
}: {
  label: string;
  placeholder: string;
  options: ShiftOption[];
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <label className="shift-select-label">
      <span>{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        <option value="">{placeholder}</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
function ShiftCheckDetail({ check }: { check: ShiftCheck }) {
  return (
    <>
      <article className="shift-card">
        <p className="shift-caption">ПРОВЕРКА</p>
        <h2>{check.description}</h2>
        <p className="shift-muted">{check.result}</p>
      </article>
      <p className="shift-body shift-muted">
        Сопоставь результат с другими источниками. Наблюдение может подтвердить
        или опровергнуть предположение.
      </p>
    </>
  );
}
function ShiftPlot({ metric }: { metric: ShiftMetric }) {
  const { points, path, min, max } = shiftPlotGeometry(
      metric.series,
      300,
      116,
      6,
    ),
    last = points.at(-1),
    middle = points[Math.floor(points.length / 2)];
  return (
    <div className="shift-plot">
      <p>{metric.unit.toUpperCase()}</p>
      <svg
        viewBox="0 0 326 140"
        role="img"
        aria-label={`График ${metric.label}: ${metric.series.map((p) => `${p.time}: ${number(p.value)}`).join("; ")}`}
      >
        <g transform="translate(26,0)">
          {[6, 58, 110].map((y, i) => (
            <g key={y}>
              <line
                x1="6"
                x2="294"
                y1={y}
                y2={y}
                stroke="#60434d"
                strokeWidth="1"
              />
              <text x="-18" y={y + 3} fill="#fff8f2" fontSize="8">
                {number(i === 0 ? max : i === 1 ? (max + min) / 2 : min)}
              </text>
            </g>
          ))}
          <path d={path} fill="none" stroke="#d50032" strokeWidth="3" />
          {points.map((point, i) => (
            <circle
              key={i}
              cx={point.x}
              cy={point.y}
              r={i === points.length - 1 ? 4 : 2}
              fill={i === points.length - 1 ? "#fff8f2" : "#d50032"}
            >
              <title>{`${point.time}: ${metricValue(metric, point.value)}`}</title>
            </circle>
          ))}
          {points[0] && (
            <text x="6" y="133" fill="#fff8f2" fontSize="8">
              {points[0].time}
            </text>
          )}
          {middle && (
            <text
              x={middle.x}
              y="133"
              textAnchor="middle"
              fill="#fff8f2"
              fontSize="8"
            >
              {middle.time}
            </text>
          )}
          {last && (
            <text x="294" y="133" textAnchor="end" fill="#fff8f2" fontSize="8">
              {last.time}
            </text>
          )}
        </g>
      </svg>
    </div>
  );
}
function ShiftScheme({
  puzzle,
  selectedId,
  onSelect,
}: {
  puzzle: ShiftPuzzle;
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const nodes = new Map(puzzle.scheme.nodes.map((n) => [n.id, n])),
    queueMetric = puzzle.metrics.find((m) => m.id === "queue");
  const node = (id: string, position: string) => {
    const item = nodes.get(id);
    return item ? (
      <button
        className={`shift-scheme-node ${position} ${selectedId === id ? "selected" : ""}`}
        onClick={() => onSelect(id)}
        aria-label={`${item.label}: ${number(item.value)} ${item.unit}`}
      >
        <span>{item.label.toUpperCase()}</span>
        <strong>{number(item.value)} / мин</strong>
      </button>
    ) : null;
  };
  const flow =
    puzzle.scheme.flows.find((f) => f.from === "capping") ??
    puzzle.scheme.flows[0];
  return (
    <div className="shift-scheme">
      <img
        className="shift-scheme-connector"
        alt=""
        src="/assets/shift/scheme-connector.svg"
      />
      <svg
        className="shift-scheme-lines"
        viewBox="0 0 350 270"
        aria-hidden="true"
      >
        {[95, 117, 139, 161]
          .slice(0, Math.min(4, nodes.get("queue")?.value ?? 0))
          .map((x) => (
            <circle key={x} cx={x} cy="220" r="7" fill="#d50032" />
          ))}
      </svg>
      {node("feed", "feed")}
      {node("capping", "capping")}
      {node("packaging", "packaging")}
      <p className="shift-scheme-time">СНИМОК {puzzle.snapshotTime}</p>
      {nodes.get("queue") && (
        <button
          className="shift-scheme-queue"
          onClick={() => onSelect("queue")}
          aria-label={`Очередь: ${nodes.get("queue")!.value}; ранее ${queueMetric?.previous}`}
        >
          <span>ОЧЕРЕДЬ: {nodes.get("queue")!.value}</span>
          <small>ранее {queueMetric?.previous}</small>
        </button>
      )}
      {flow && (
        <button
          className="shift-flow-target"
          aria-label="Наблюдать движение между участками"
          onClick={() => onSelect(flow.id)}
        />
      )}
      <div className="shift-scheme-extra">
        {puzzle.scheme.nodes
          .filter(
            (n) => !["feed", "capping", "packaging", "queue"].includes(n.id),
          )
          .map((n) => (
            <button key={n.id} onClick={() => onSelect(n.id)}>
              {n.label}: {number(n.value)} / мин
            </button>
          ))}
      </div>
    </div>
  );
}
function ShiftCriteria({
  onBack,
  onCareer,
}: {
  onBack: () => void;
  onCareer: () => void;
}) {
  return (
    <>
      <p className="shift-caption">КАК ПРОВЕРЯЕТСЯ ОБЪЯСНЕНИЕ</p>
      <article className="shift-card shift-blush">
        <p className="shift-caption">СВЯЗЬ ДАННЫХ · ДО 20 БАЛЛОВ</p>
        <h2>Участок → событие → наблюдение</h2>
        <p className="shift-muted">
          Сначала локализуй изменение, затем сопоставь возможную причину с
          независимым подтверждением. Отдели проверенный факт от предположения.
        </p>
      </article>
      <p className="shift-body shift-muted">
        Подходят разные достаточные наборы источников. Не требуется открыть всё
        или выбрать ровно три карточки. Противоречия нужно проверить.
      </p>
      <article className="shift-card">
        <p className="shift-caption">СЛЕДУЮЩИЙ ШАГ · ДО 10 БАЛЛОВ</p>
        <h2>Действовать в рамках роли</h2>
        <p className="shift-muted">
          Предложи безопасный следующий шаг и укажи ответственного. Передавай
          команде проверенные данные.
        </p>
      </article>
      <button className="shift-primary" onClick={onBack}>
        Вернуться к своему выводу
      </button>
      <button className="shift-link" onClick={onCareer}>
        Узнать о профессиях →
      </button>
      <p className="shift-small shift-muted">
        Свободные заметки не оцениваются. Проверяются утверждения конструктора и
        выбранные основания.
      </p>
    </>
  );
}
function ShiftResult({
  result,
  onReview,
  onCareer,
  onExit,
}: {
  result: ShiftCompletionResult;
  onReview: () => void;
  onCareer: () => void;
  onExit: () => void;
}) {
  return (
    <>
      <p className="shift-caption">
        ОБОСНОВАННЫЙ ВЫВОД ·{" "}
        {result.alreadyCompleted
          ? "ТРЕНИРОВКА"
          : `+${result.pointsAwarded} БАЛЛОВ`}
      </p>
      <article className="shift-card shift-blush">
        <p className="shift-caption">СВЯЗЬ ДАННЫХ</p>
        <h2>Участок → событие → наблюдение</h2>
        <p className="shift-muted">{result.explanation}</p>
      </article>
      <p className="shift-body shift-muted">
        Это один допустимый путь. Другой набор источников тоже подходит, если
        подтверждает причину и не противоречит данным.
      </p>
      {result.outcome && (
        <article className="shift-card">
          <p className="shift-caption">СЛЕДУЮЩИЙ ШАГ И ПОСЛЕДСТВИЯ</p>
          <h2>{result.outcome.summary}</h2>
          <dl className="shift-consequences">
            <div>
              <dt>До согласования</dt>
              <dd>{result.outcome.before}</dd>
            </div>
            <div>
              <dt>После согласования</dt>
              <dd>{result.outcome.after}</dd>
            </div>
          </dl>
        </article>
      )}
      {result.assessment && (
        <div className="shift-assessment" aria-label="Разбор по критериям">
          <span>
            Локализация <strong>{result.assessment.localization}/10</strong>
          </span>
          <span>
            Причина <strong>{result.assessment.cause}/10</strong>
          </span>
          <span>
            Следующий шаг <strong>{result.assessment.nextStep}/10</strong>
          </span>
        </div>
      )}
      <button className="shift-primary" onClick={onReview}>
        Вернуться к своему выводу
      </button>
      <button className="shift-link" onClick={onCareer}>
        Узнать о профессиях →
      </button>
      <button className="shift-secondary" onClick={onExit}>
        К заданиям
      </button>
      <p className="shift-small shift-muted">
        {result.alreadyCompleted
          ? "За этот вариант баллы уже начислены. Повтор доступен для тренировки."
          : "Баллы начислены за обоснование и согласованный следующий шаг."}{" "}
        Игровой результат не оценивает профессиональную пригодность.
      </p>
    </>
  );
}
