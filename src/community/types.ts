import type { StaffRole } from "../api";
import type {
  ActivityCompletion,
  CareerEvent,
  Exchange,
  LedgerEntry,
  Registration,
  Reward,
} from "../types";

export interface CommunityData {
  user: { id: string; role: StaffRole };
  balance: number;
  events: CareerEvent[];
  registrations: Registration[];
  activityCompletions: ActivityCompletion[];
  rewards: Reward[];
  exchanges: Exchange[];
  ledger: LedgerEntry[];
}
