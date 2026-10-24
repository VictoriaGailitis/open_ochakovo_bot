import type {
  ShiftDraft,
  ShiftFact,
  ShiftObservation,
  ShiftPuzzle,
  ShiftSeriesPoint,
  ShiftView,
} from "./ShiftTypes";

export const MAX_SHIFT_OBSERVATIONS = 32;
const views: ShiftView[] = [
  "overview",
  "metric",
  "scheme",
  "journal",
  "event",
  "checks",
  "check",
  "observations",
  "conclusion",
  "criteria",
];
export function newShiftDraft(): ShiftDraft {
  return {
    version: 1,
    view: "overview",
    metricId: "",
    eventId: "",
    checkId: "",
    schemeId: "",
    hypothesis: "",
    observations: [],
    conclusion: {
      observedChange: "",
      explanation: "",
      evidence: [],
      nextStep: "",
      responsible: "",
    },
    hintIndex: -1,
    composingFactId: "",
    composingNote: "",
    editingFactId: "",
  };
}
const record = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
const limited = (value: unknown, max = 2000) =>
  typeof value === "string" ? value.slice(0, max) : "";
export function makeShiftObservation(
  fact: ShiftFact,
  note = "",
): ShiftObservation {
  return {
    factId: fact.id,
    source: fact.source,
    time: fact.time,
    fact: fact.text,
    note: limited(note),
  };
}
export function normalizeShiftDraft(
  value: unknown,
  puzzle: ShiftPuzzle,
): ShiftDraft {
  const saved = record(value),
    base = newShiftDraft(),
    facts = new Map(puzzle.facts.map((f) => [f.id, f])),
    seen = new Set<string>();
  const observations: ShiftObservation[] = [];
  if (Array.isArray(saved.observations))
    for (const item of saved.observations) {
      const raw = record(item),
        id = limited(raw.factId, 100),
        fact = facts.get(id);
      if (
        fact &&
        !seen.has(id) &&
        observations.length < MAX_SHIFT_OBSERVATIONS
      ) {
        seen.add(id);
        observations.push(makeShiftObservation(fact, limited(raw.note)));
      }
    }
  const conclusion = record(saved.conclusion);
  const option = (
    key: "observedChange" | "explanation" | "nextStep" | "responsible",
  ) =>
    puzzle.conclusion[key].some((o) => o.id === conclusion[key])
      ? String(conclusion[key])
      : "";
  return {
    ...base,
    view: views.includes(saved.view as ShiftView)
      ? (saved.view as ShiftView)
      : "overview",
    metricId: puzzle.metrics.some((m) => m.id === saved.metricId)
      ? String(saved.metricId)
      : "",
    eventId: puzzle.journal.some((e) => e.id === saved.eventId)
      ? String(saved.eventId)
      : "",
    checkId: puzzle.checks.some((c) => c.id === saved.checkId)
      ? String(saved.checkId)
      : "",
    schemeId: [...puzzle.scheme.nodes, ...puzzle.scheme.flows].some(
      (n) => n.id === saved.schemeId,
    )
      ? String(saved.schemeId)
      : "",
    hypothesis: limited(saved.hypothesis),
    observations,
    conclusion: {
      observedChange: option("observedChange"),
      explanation: option("explanation"),
      nextStep: option("nextStep"),
      responsible: option("responsible"),
      evidence: Array.isArray(conclusion.evidence)
        ? [
            ...new Set(
              conclusion.evidence.filter(
                (id): id is string => typeof id === "string" && seen.has(id),
              ),
            ),
          ]
        : [],
    },
    hintIndex:
      typeof saved.hintIndex === "number" && Number.isInteger(saved.hintIndex)
        ? Math.min(Math.max(saved.hintIndex, -1), puzzle.hints.length - 1)
        : -1,
    composingFactId: facts.has(String(saved.composingFactId))
      ? String(saved.composingFactId)
      : "",
    composingNote: limited(saved.composingNote),
    editingFactId: seen.has(String(saved.editingFactId))
      ? String(saved.editingFactId)
      : "",
  };
}
export function pinShiftFact(
  draft: ShiftDraft,
  fact: ShiftFact,
  note = "",
): ShiftDraft {
  if (
    draft.observations.some((o) => o.factId === fact.id) ||
    draft.observations.length >= MAX_SHIFT_OBSERVATIONS
  )
    return draft;
  return {
    ...draft,
    observations: [...draft.observations, makeShiftObservation(fact, note)],
    composingFactId: "",
    composingNote: "",
  };
}
export function removeShiftObservation(
  draft: ShiftDraft,
  id: string,
): ShiftDraft {
  return {
    ...draft,
    observations: draft.observations.filter((o) => o.factId !== id),
    conclusion: {
      ...draft.conclusion,
      evidence: draft.conclusion.evidence.filter((value) => value !== id),
    },
    editingFactId: draft.editingFactId === id ? "" : draft.editingFactId,
  };
}
export function updateShiftNote(
  draft: ShiftDraft,
  id: string,
  note: string,
): ShiftDraft {
  return {
    ...draft,
    observations: draft.observations.map((o) =>
      o.factId === id ? { ...o, note: limited(note) } : o,
    ),
  };
}
export function shiftConclusionReady(draft: ShiftDraft) {
  const c = draft.conclusion,
    available = new Set(draft.observations.map((o) => o.factId));
  return Boolean(
    c.observedChange &&
    c.explanation &&
    c.nextStep &&
    c.responsible &&
    c.evidence.length &&
    c.evidence.every((id) => available.has(id)),
  );
}
export function shiftClockSeconds(time: string): number | null {
  const match = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(time);
  if (!match) return null;
  const hours = Number(match[1]),
    minutes = Number(match[2]),
    seconds = Number(match[3] ?? 0);
  return hours < 24 && minutes < 60 && seconds < 60
    ? hours * 3600 + minutes * 60 + seconds
    : null;
}
export function shiftPlotGeometry(
  series: ShiftSeriesPoint[],
  width = 300,
  height = 116,
  padding = 12,
) {
  const finite = series.filter((point) => Number.isFinite(point.value));
  if (!finite.length) return { points: [], path: "", min: 0, max: 1 };
  const low = Math.min(...finite.map((p) => p.value)),
    high = Math.max(...finite.map((p) => p.value));
  const min = low >= 0 ? 0 : low - Math.max(Math.abs(low) * 0.2, 1),
    max = high > 0 ? high * 1.2 : 1;
  const times = finite.map((point) => shiftClockSeconds(point.time));
  const timed =
    times.every((t, i) => t !== null && (i === 0 || t >= times[i - 1]!)) &&
    times.at(-1)! > times[0]!;
  const points = finite.map((point, index) => ({
    ...point,
    x:
      padding +
      (timed
        ? (times[index]! - times[0]!) / (times.at(-1)! - times[0]!)
        : finite.length === 1
          ? 0.5
          : index / (finite.length - 1)) *
        (width - 2 * padding),
    y:
      height -
      padding -
      ((point.value - min) / (max - min)) * (height - 2 * padding),
  }));
  return {
    points,
    path: points
      .map((p, i) => `${i ? "L" : "M"}${p.x.toFixed(2)},${p.y.toFixed(2)}`)
      .join(" "),
    min,
    max,
  };
}
