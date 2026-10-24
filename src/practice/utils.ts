import type { Placement } from "./types";

export const goalLabels = {
  planned: "Запланирована",
  in_progress: "В работе",
  review: "На проверке",
  approved: "Подтверждена",
};
export const practiceLabels = {
  scheduled: "Скоро начало",
  active: "Практика идёт",
  completed: "Завершена",
  cancelled: "Отменена",
};
export const requestLabels = {
  received: "Получено",
  in_progress: "В работе",
  resolved: "Решено",
};
export const meetingLabels = {
  scheduled: "Запланирована",
  completed: "Состоялась",
  cancelled: "Отменена",
};
export function date(value: string) {
  return new Date(
    value.length === 10 ? value + "T12:00:00+03:00" : value,
  ).toLocaleDateString("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "numeric",
    month: "long",
  });
}
export function time(value: string) {
  return new Date(value).toLocaleTimeString("ru-RU", {
    timeZone: "Europe/Moscow",
    hour: "2-digit",
    minute: "2-digit",
  });
}
export function calendarDays(month: string) {
  const [year, m] = month.split("-").map(Number);
  const offset = (new Date(Date.UTC(year, m - 1, 1)).getUTCDay() + 6) % 7;
  const count = new Date(Date.UTC(year, m, 0)).getUTCDate();
  return Array.from({ length: Math.ceil((offset + count) / 7) * 7 }, (_, i) => {
    const d = i - offset + 1;
    return d > 0 && d <= count
      ? `${month}-${String(d).padStart(2, "0")}`
      : null;
  });
}
export function shiftMonth(month: string, delta: number) {
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1 + delta, 1)).toISOString().slice(0, 7);
}
export function moscowDate(value: string) {
  const d = new Date(new Date(value).getTime() + 3 * 60 * 60 * 1000);
  return d.toISOString().slice(0, 10);
}
export function localInput(value: string) {
  return new Date(new Date(value).getTime() + 3 * 3600000)
    .toISOString()
    .slice(0, 16);
}
export function progress(p: Placement, today: string) {
  const start = Date.parse(p.start_date + "T00:00:00Z"),
    end = Date.parse(p.end_date + "T00:00:00Z");
  const day = Date.parse(today + "T00:00:00Z");
  return Math.max(
    0,
    Math.min(
      100,
      Math.round(((day - start) / Math.max(86400000, end - start)) * 100),
    ),
  );
}
export function report(p: Placement) {
  return [
    `Практика: ${p.title}`,
    `Практикант: ${p.studentName}`,
    `${date(p.start_date)} — ${date(p.end_date)}`,
    `Наставник: ${p.mentor?.name ?? "Ещё не назначен"}`,
    "",
    "ЦЕЛИ И РЕЗУЛЬТАТЫ",
    ...p.goals.map(
      (g) =>
        `${g.title} — ${goalLabels[g.status]}\nКритерии: ${g.criteria}\n${g.mentor_comment}`,
    ),
    "",
    "ОБРАТНАЯ СВЯЗЬ",
    ...p.feedback.map(
      (f) => `${date(f.created)} · ${f.author_name}\n${f.body}`,
    ),
  ].join("\n");
}
