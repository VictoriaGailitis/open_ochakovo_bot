import type { StaffRole } from "../api";

export function staffHome(role: StaffRole): string {
  return role === "employee"
    ? "employee"
    : role === "mentor"
      ? "mentor"
      : "practice";
}

/** Community access depends on a staff account, not an assigned practice period. */
export function staffDestination(role: StaffRole, requested: string): string {
  if (requested === "community" || requested === "employee") return requested;
  return staffHome(role);
}
