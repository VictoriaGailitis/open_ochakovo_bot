import { test } from "node:test";
import assert from "node:assert/strict";
import type { ShiftPuzzle } from "./ShiftTypes";
import {
  MAX_SHIFT_OBSERVATIONS,
  makeShiftObservation,
  newShiftDraft,
  normalizeShiftDraft,
  pinShiftFact,
  removeShiftObservation,
  shiftConclusionReady,
  shiftPlotGeometry,
  updateShiftNote,
} from "./shiftMechanics";
const puzzle: ShiftPuzzle = {
  snapshotTime: "14:07:30",
  measurementWindow: "последняя минута",
  modelNote: "Учебная модель",
  metrics: [],
  scheme: { nodes: [], flows: [] },
  journal: [],
  checks: [],
  facts: Array.from({ length: 40 }, (_, i) => ({
    id: `f${i}`,
    source: `Источник ${i}`,
    time: "14:07",
    text: `Факт ${i}`,
  })),
  conclusion: {
    observedChange: [{ id: "change", label: "Изменение" }],
    explanation: [{ id: "reason", label: "Объяснение" }],
    nextStep: [{ id: "action", label: "Действие" }],
    responsible: [{ id: "owner", label: "Ответственный" }],
  },
  hints: ["Как сравнить данные?"],
};
test("new shift session has no preselected observations or conclusion", () => {
  const draft = newShiftDraft();
  assert.equal(draft.view, "overview");
  assert.deepEqual(draft.observations, []);
  assert.deepEqual(draft.conclusion.evidence, []);
  assert.equal(shiftConclusionReady(draft), false);
});
test("restored observations use canonical source and fact, deduplicate IDs and reject unknown claims", () => {
  const saved = {
    view: "unknown",
    observations: [
      {
        factId: "f0",
        source: "подмена",
        time: "ошибка",
        fact: "готовый ответ",
        note: "Моя заметка",
      },
      { factId: "f0" },
      { factId: "missing" },
    ],
    conclusion: {
      observedChange: "change",
      explanation: "not-an-option",
      evidence: ["f0", "missing", "f0"],
      nextStep: "action",
      responsible: "owner",
    },
  };
  const draft = normalizeShiftDraft(saved, puzzle);
  assert.equal(draft.view, "overview");
  assert.deepEqual(draft.observations, [
    makeShiftObservation(puzzle.facts[0], "Моя заметка"),
  ]);
  assert.equal(draft.conclusion.explanation, "");
  assert.deepEqual(draft.conclusion.evidence, ["f0"]);
});
test("pinning is manual, allows more than five observations and never preselects proof", () => {
  let draft = newShiftDraft();
  for (const fact of puzzle.facts) draft = pinShiftFact(draft, fact);
  assert.equal(draft.observations.length, MAX_SHIFT_OBSERVATIONS);
  assert.ok(draft.observations.length > 5);
  assert.deepEqual(draft.conclusion.evidence, []);
  assert.equal(pinShiftFact(draft, puzzle.facts[0]), draft);
});
test("removing an observation removes its proof reference; note edits preserve canonical fact", () => {
  let draft = pinShiftFact(newShiftDraft(), puzzle.facts[0]);
  draft = {
    ...draft,
    conclusion: {
      observedChange: "change",
      explanation: "reason",
      nextStep: "action",
      responsible: "owner",
      evidence: ["f0"],
    },
  };
  assert.equal(shiftConclusionReady(draft), true);
  const updated = updateShiftNote(draft, "f0", "a".repeat(2400));
  assert.equal(updated.observations[0].note.length, 2000);
  assert.equal(updated.observations[0].fact, puzzle.facts[0].text);
  assert.equal(draft.observations[0].note, "");
  const removed = removeShiftObservation(updated, "f0");
  assert.deepEqual(removed.conclusion.evidence, []);
  assert.equal(shiftConclusionReady(removed), false);
});
test("graph handles stable readings, one reading, nonfinite values and original temporal order", () => {
  for (const series of [
    [],
    [{ time: "14:00", value: 42 }],
    [
      { time: "14:00", value: 60 },
      { time: "14:01", value: 60 },
    ],
    [{ time: "14:00", value: NaN }],
  ]) {
    const g = shiftPlotGeometry(series);
    assert.ok(!g.path.includes("NaN"));
    assert.ok(!g.path.includes("Infinity"));
  }
  const g = shiftPlotGeometry([
    { time: "14:06", value: 60 },
    { time: "14:07", value: 42 },
  ]);
  assert.ok(g.points[0].x < g.points[1].x);
  assert.ok(g.points[0].y < g.points[1].y);
  assert.deepEqual(
    g.points.map((p) => p.value),
    [60, 42],
  );
});
test("plot uses actual elapsed clock time for nonuniform intervals", () => {
  const series = [
    { time: "14:06:30", value: 60 },
    { time: "14:06:40", value: 42 },
    { time: "14:07:30", value: 42 },
  ];
  const g = shiftPlotGeometry(series, 300, 116, 0);
  assert.equal(g.points[0].x, 0);
  assert.equal(g.points[1].x, 50);
  assert.equal(g.points[2].x, 300);
});
test("duplicate timestamps and malformed clock labels never produce invalid plot geometry", () => {
  for (const times of [
    ["14:07:30", "14:07:30"],
    ["bad", "14:07:30"],
    ["25:99:99", "14:07:30"],
    ["14:07:30", "14:06:30"],
  ]) {
    const g = shiftPlotGeometry(
      times.map((time, i) => ({ time, value: i + 1 })),
    );
    assert.ok(
      g.points.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)),
    );
    assert.ok(g.points[0].x < g.points[1].x);
  }
});
