import type { CompletionResult, GamePlayerProps, Task } from "./types";

export interface ShiftSeriesPoint {
  time: string;
  value: number;
}
export interface ShiftFact {
  id: string;
  source: string;
  time: string;
  text: string;
}
export interface ShiftValueFormat {
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
  /** Literal suffixes include their own separating space. */
  suffix?: string;
  compactSuffix?: string;
  comparisonSuffix?: string;
}
export interface ShiftMetric {
  id: string;
  shortLabel?: string;
  highlight?: boolean;
  format?: ShiftValueFormat;
  label: string;
  value: number;
  unit: string;
  previous: number;
  series: ShiftSeriesPoint[];
  factId: string;
  historyFactId?: string;
  source: string;
  time: string;
}
export interface ShiftSchemeNode {
  id: string;
  /** Coordinates use the existing 350 × 270 design canvas. */
  position?: { x: number; y: number };
  display?: "card" | "queue" | "extra";
  metricId?: string;
  format?: ShiftValueFormat;
  label: string;
  value: number;
  unit: string;
  factId: string;
}
export interface ShiftSchemeFlow {
  id: string;
  from: string;
  to: string;
  label: string;
  factId: string;
  primary?: boolean;
}
export interface ShiftJournalEvent {
  id: string;
  time: string;
  title: string;
  detail: string;
  factId: string;
}
export interface ShiftCheck {
  id: string;
  title: string;
  description: string;
  result: string;
  factId: string;
}
export interface ShiftOption {
  id: string;
  label: string;
}
export interface ShiftPuzzle {
  snapshotTime: string;
  measurementWindow: string;
  modelNote: string;
  metrics: ShiftMetric[];
  scheme: { nodes: ShiftSchemeNode[]; flows: ShiftSchemeFlow[] };
  journal: ShiftJournalEvent[];
  checks: ShiftCheck[];
  facts: ShiftFact[];
  conclusion: {
    observedChange: ShiftOption[];
    explanation: ShiftOption[];
    nextStep: ShiftOption[];
    responsible: ShiftOption[];
  };
  hints: string[];
}
export type ShiftTask = Omit<Task, "game" | "puzzle"> & {
  game: "shift";
  puzzle: ShiftPuzzle;
};
export type ShiftGameProps = Omit<GamePlayerProps, "task"> & {
  task: ShiftTask;
};
export interface ShiftCompletionResult extends CompletionResult {
  outcome?: { summary: string; before: string; after: string };
  assessment?: { localization: number; cause: number; nextStep: number };
}
export interface ShiftObservation {
  factId: string;
  source: string;
  time: string;
  fact: string;
  note: string;
}
export interface ShiftConclusion {
  observedChange: string;
  explanation: string;
  evidence: string[];
  nextStep: string;
  responsible: string;
}
export type ShiftView =
  | "overview"
  | "metric"
  | "scheme"
  | "journal"
  | "event"
  | "checks"
  | "check"
  | "observations"
  | "conclusion"
  | "criteria";
export interface ShiftDraft {
  version: 1;
  view: ShiftView;
  metricId: string;
  eventId: string;
  checkId: string;
  schemeId: string;
  hypothesis: string;
  observations: ShiftObservation[];
  conclusion: ShiftConclusion;
  hintIndex: number;
  composingFactId: string;
  composingNote: string;
  editingFactId: string;
}
