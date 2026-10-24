export interface ReferralInfo {
  code: string;
  created: string;
  stats: { applications: number; merchPending: number; merchIssued: number };
}
export type ReferralClient = <T>(
  path: string,
  method?: string,
  body?: unknown,
) => Promise<T>;
export const normalizeReferralCode = (code: string) =>
  code.trim().toUpperCase();
export const validReferralCode = (code: string) =>
  !code.trim() || /^OC-[A-HJ-NP-Z2-9]{8}$/.test(normalizeReferralCode(code));
