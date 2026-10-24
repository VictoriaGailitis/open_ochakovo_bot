import type { ShiftPuzzle } from "./ShiftTypes";

export type GameKind =
  "shift" | "signal" | "movement" | "lab" | "delivery" | "history";
export interface Point {
  x: number;
  y: number;
}
export interface Rule {
  condition: string;
  output: string;
}
export interface SignalPuzzle {
  stream: { color: string; marked: boolean }[];
  allowedConditions: string[];
  outputs: string[];
  rule: string;
  maxRules: number;
}
export interface MovementPuzzle {
  width: number;
  height: number;
  source: Point & { direction: number };
  target: Point & { direction: number };
  maxGears: number;
}
export interface LabPuzzle {
  samples: { id: string; name: string; properties: Record<string, string> }[];
  tests: { id: string; label: string }[];
  observations: Record<string, string>;
}
export interface Batch {
  id: string;
  product: string;
  cells: number[][];
  reserved: boolean;
  location: Point;
}
export interface Placement extends Point {
  batchId: string;
  rotated: boolean;
}
export interface DeliveryPuzzle {
  width: number;
  height: number;
  batches: Batch[];
  order: { product: string; quantity: number }[];
  start: Point;
  warehouse: { width: number; height: number };
}
export interface HistoryPuzzle {
  questions: {
    id: string;
    text: string;
    options: { id: string; text: string }[];
    source: string;
  }[];
}
export interface Task {
  id: string;
  game: GameKind;
  level: number;
  title: string;
  description: string;
  direction: string;
  points: number;
  duration: string;
  puzzle:
    | ShiftPuzzle
    | SignalPuzzle
    | MovementPuzzle
    | LabPuzzle
    | DeliveryPuzzle
    | HistoryPuzzle;
  explanation?: string;
  offerId?: string;
  demo?: boolean;
}
export interface CompletionResult {
  correct: boolean;
  pointsAwarded: number;
  alreadyCompleted: boolean;
  explanation: string;
  errors: string[];
  balance?: number;
  progress?: unknown;
}
export interface GamePlayerProps {
  task: Task;
  draft: unknown;
  draftRevision?: number;
  onSave: (draft: unknown, revision: number) => Promise<void>;
  onComplete: (solution: unknown) => Promise<CompletionResult>;
  onCareer: (direction: string) => void;
  onExit: () => void;
}
