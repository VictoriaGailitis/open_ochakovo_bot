import type { GameDefinition, Task } from "./games/types";

export interface Profile {
  fullName: string;
  contact: string;
  birthDate: string;
  direction: string;
  availability: string;
  education: string;
  schedule: string;
  consent: boolean;
  futureContact: boolean;
}
export interface Offer {
  id: string;
  title: string;
  direction: string;
  type: string;
  location: string;
  schedule: string;
  pay: string;
  description: string;
  tasks: string[];
  requirements: string[];
  demo: boolean;
  deadline?: string;
}
export interface CareerEvent {
  id: string;
  title: string;
  date: string;
  startTime: string;
  location: string;
  type: string;
  description: string;
  capacity: number;
  remaining: number;
  demo: boolean;
  requirements?: string[];
  program?: string[];
  activities?: EventActivity[];
}
export interface EventActivity {
  id: string;
  eventId: string;
  title: string;
  description: string;
  points: number;
  active: boolean;
}
export interface ActivityCompletion {
  activityId: string;
  eventId: string;
  completedAt: string;
  awardedPoints?: number;
}
export interface ActivityScanResult {
  activity: EventActivity;
  event: { id: string; title: string };
  completion: ActivityCompletion;
  pointsAwarded: number;
  alreadyCompleted: boolean;
  balance: number;
}
export interface Reward {
  id: string;
  title: string;
  cost: number;
  description: string;
  stock: number;
  remaining: number;
  demo: boolean;
}
export interface Progress {
  task: string;
  draft: unknown;
  completed: unknown | null;
  revision?: number;
  draft_revision?: number;
}
export interface Application {
  id: string;
  offer: string;
  status: string;
  created: string;
  profile: Profile;
  userId?: string;
}
export interface Registration {
  id: string;
  event: string;
  status: string;
  created: string;
}
export interface Exchange {
  id: string;
  reward: string;
  created: string;
}
export interface LedgerEntry {
  id: string;
  reason: string;
  delta: number;
  created: string;
}
export interface Catalog {
  games?: GameDefinition[];
  tasks: Task[];
  offers: Offer[];
  events: CareerEvent[];
  rewards: Reward[];
}
export interface Bootstrap {
  routeCompleted?: boolean;
  routeProgress?: {
    completed: number;
    total: number;
    taskIds: string[];
    completedTaskIds: string[];
  };
  user?: { id: string };
  userId?: string;
  mode?: string;
  profile: Profile | null;
  balance: number;
  progress: Progress[];
  applications: Application[];
  registrations: Registration[];
  exchanges: Exchange[];
  ledger: LedgerEntry[];
  catalog: Catalog;
  activityCompletions?: ActivityCompletion[];
}
export const DIRECTIONS: Record<string, string> = {
  undecided: "Пока не определился",
  lab: "Лаборатория и качество",
  production: "Производство и розлив",
  technology: "Пищевые технологии",
  warehouse: "Склад и логистика",
  automation: "Автоматизация",
  mechanics: "Механика и оборудование",
};
export const STATUSES: Record<string, string> = {
  sent: "Отправлен",
  contacted: "HR связался",
  registered: "Запись подтверждена",
  received: "Получен",
  new: "Получен",
  submitted: "Получен",
  reviewing: "На рассмотрении",
  invited: "Приглашение",
  accepted: "Принят",
  rejected: "Завершён",
  withdrawn: "Отозван",
  confirmed: "Запись подтверждена",
  cancelled: "Отменена",
};
