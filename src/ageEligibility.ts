export type AgeEligibility = "adult" | "underage" | "invalid";

export function moscowCalendarDate(now = new Date()): string {
  return new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Europe/Moscow",
  }).format(now);
}

/** Calendar birthdays, including the day of turning 18, use Moscow time. */
export function registrationAge(
  birthday: string,
  today = moscowCalendarDate(),
): AgeEligibility {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(birthday)) return "invalid";
  const parsed = new Date(`${birthday}T00:00:00Z`);
  if (
    !Number.isFinite(parsed.getTime()) ||
    parsed.toISOString().slice(0, 10) !== birthday ||
    birthday > today
  )
    return "invalid";
  const age =
    Number(today.slice(0, 4)) -
    Number(birthday.slice(0, 4)) -
    (today.slice(5) < birthday.slice(5) ? 1 : 0);
  if (age < 0 || age > 100) return "invalid";
  return age < 18 ? "underage" : "adult";
}
