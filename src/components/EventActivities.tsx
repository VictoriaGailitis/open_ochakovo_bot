import { useId } from "react";
import type { ActivityCompletion, CareerEvent } from "../types";
import "./event-activities.css";

function pointsLabel(points: number) {
  const lastTwo = Math.abs(points) % 100;
  const last = Math.abs(points) % 10;
  const noun =
    lastTwo >= 11 && lastTwo <= 14
      ? "баллов"
      : last === 1
        ? "балл"
        : last >= 2 && last <= 4
          ? "балла"
          : "баллов";
  return `+${points} ${noun}`;
}

function completionDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Europe/Moscow",
  }).format(date);
}

function ScanIcon() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5" />
      <path d="M7 7h3v3H7zM14 7h3v3h-3zM7 14h3v3H7zM14 14h3v3h-3z" />
    </svg>
  );
}

export function EventActivities({
  event,
  completions,
  onScan,
}: {
  event: CareerEvent;
  completions: ActivityCompletion[];
  onScan: () => void;
}) {
  const headingId = useId();
  const activities = event.activities ?? [];
  const completedById = new Map(
    completions
      .filter((completion) => completion.eventId === event.id)
      .map((completion) => [completion.activityId, completion]),
  );
  const completedCount = activities.filter((activity) =>
    completedById.has(activity.id),
  ).length;
  const canScan = activities.some(
    (activity) => activity.active && !completedById.has(activity.id),
  );

  return (
    <section className="event-activities" aria-labelledby={headingId}>
      <div className="event-activities-heading">
        <h2 id={headingId}>Активности мероприятия</h2>
        {activities.length > 0 && (
          <p className="small muted" aria-live="polite">
            Выполнено {completedCount} из {activities.length}
          </p>
        )}
      </div>

      {activities.length === 0 ? (
        <p className="event-activities-empty small muted">
          Активности появятся здесь, когда организаторы подготовят программу.
        </p>
      ) : (
        <ul className="event-activities-list">
          {activities.map((activity) => {
            const completion = completedById.get(activity.id);
            const formattedDate = completion
              ? completionDate(completion.completedAt)
              : null;
            const unavailable = !activity.active && !completion;
            return (
              <li
                key={activity.id}
                className={`event-activity${completion ? " event-activity-completed" : ""}${unavailable ? " event-activity-unavailable" : ""}`}
              >
                <div className="event-activity-heading">
                  <h3>{activity.title}</h3>
                  <span className="event-activity-points">
                    {pointsLabel(completion?.awardedPoints ?? activity.points)}
                  </span>
                </div>
                <p className="small muted">{activity.description}</p>
                <div className="event-activity-footer">
                  <p
                    className={`event-activity-status small${completion ? " event-activity-status-completed" : ""}`}
                  >
                    {completion ? (
                      <>
                        <span aria-hidden="true">✓ </span>Выполнено
                      </>
                    ) : unavailable ? (
                      "Пока недоступна"
                    ) : (
                      "Ожидает QR-код"
                    )}
                  </p>
                  {completion && formattedDate && (
                    <time
                      className="small muted"
                      dateTime={completion.completedAt}
                    >
                      {formattedDate} МСК
                    </time>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {canScan && (
        <div className="event-activities-scan">
          <p className="small muted">
            Участвуй на площадке и сканируй QR-коды активностей — баллы появятся
            после подтверждения.
          </p>
          <button
            type="button"
            className="button button-primary"
            onClick={onScan}
            aria-label={`Сканировать QR-код для мероприятия «${event.title}»`}
          >
            <ScanIcon />
            Сканировать QR-код
          </button>
        </div>
      )}
    </section>
  );
}
