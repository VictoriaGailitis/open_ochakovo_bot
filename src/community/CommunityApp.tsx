import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { staffApi, loadStaffMedia, type StaffRole } from "../api";
import { EventActivities } from "../components/EventActivities";
import { QrScanner } from "../components/QrScanner";
import { Learning } from "../learning/Learning";
import { ReferralCard } from "../referrals";
import type {
  ActivityScanResult,
  CareerEvent,
  LedgerEntry,
  Reward,
} from "../types";
import type { CommunityData } from "./types";
import { staffHome } from "./staffRoutes";
import "./community.css";

function route() {
  return location.hash
    .replace(/^#\/?/, "")
    .split("/")
    .map((part) => {
      try {
        return decodeURIComponent(part);
      } catch {
        return part;
      }
    });
}
function date(value: string, withTime = false) {
  const parsed = new Date(
    value.length === 10 ? value + "T12:00:00+03:00" : value,
  );
  if (!Number.isFinite(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "numeric",
    month: "long",
    ...(withTime ? ({ hour: "2-digit", minute: "2-digit" } as const) : {}),
  }).format(parsed);
}
function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="card community-empty">
      <p>{children}</p>
    </div>
  );
}
function eventStarted(event: CareerEvent) {
  return (
    new Date(
      `${event.date}T${event.startTime || "12:00"}:00+03:00`,
    ).getTime() <= Date.now()
  );
}
function ledgerTitle(entry: LedgerEntry, data: CommunityData) {
  if (entry.reason.startsWith("event-activity:")) {
    const id = entry.reason.slice("event-activity:".length);
    for (const event of data.events) {
      const activity = event.activities?.find((item) => item.id === id);
      if (activity) return `${activity.title} · ${event.title}`;
    }
    return "Активность мероприятия";
  }
  if (entry.reason.startsWith("exchange:")) {
    return (
      "Обмен: " +
      (data.rewards.find((reward) => reward.id === entry.reason.slice(9))
        ?.title ?? "награда")
    );
  }
  if (/^(material|learning|quiz):/.test(entry.reason))
    return "Проверка знаний по материалу";
  if (entry.reason === "task:history-1")
    return "История компании · проверка знаний";
  if (entry.reason.startsWith("referral:")) return "Программа «Приведи друга»";
  return "Начисление баллов";
}

export function CommunityApp({
  role,
  onLogout,
}: {
  role: StaffRole;
  onLogout: () => Promise<void>;
}) {
  const [current, setCurrent] = useState(route);
  const [data, setData] = useState<CommunityData | null>(null);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [pointsView, setPointsView] = useState<"rewards" | "history">(
    "rewards",
  );
  const heading = useRef<HTMLElement>(null),
    request = useRef(0),
    lock = useRef(false);
  const screen = current[1] || "materials",
    id = current[2];
  const root = current[0] === "employee" ? "employee" : "community";
  const go = (page: string, item?: string) => {
    location.hash = `/${root}/${page}${item ? "/" + encodeURIComponent(item) : ""}`;
  };
  const refresh = useCallback(async () => {
    const sequence = ++request.current;
    const result = await staffApi<CommunityData>("/community/bootstrap");
    if (sequence === request.current) setData(result);
  }, []);
  useEffect(() => {
    let alive = true;
    void refresh()
      .catch((failure) => {
        if (alive)
          setError(
            failure instanceof Error
              ? failure.message
              : "Не удалось загрузить сообщество.",
          );
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
      request.current++;
    };
  }, [refresh]);
  useEffect(() => {
    const changed = () => {
      setCurrent(route());
      setError("");
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [current.join("/")]);
  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(""), 5000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  async function run(path: string, method: string, message: string) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await staffApi(path, method, {});
      setNotice(message);
      await refresh();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Не удалось сохранить. Попробуй ещё раз.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function scan(code: string) {
    const result = await staffApi<ActivityScanResult>(
      "/event-activities/scan",
      "POST",
      { code },
    );
    setData((previous) =>
      previous
        ? {
            ...previous,
            balance: result.balance,
            activityCompletions: [
              ...previous.activityCompletions.filter(
                (completion) =>
                  completion.activityId !== result.completion.activityId,
              ),
              result.completion,
            ],
          }
        : previous,
    );
    await refresh().catch(() =>
      setNotice(
        "Активность засчитана. Обнови страницу, чтобы увидеть весь прогресс.",
      ),
    );
    return result;
  }
  function back(page = "events") {
    return (
      <button
        className="button-ghost back-link"
        type="button"
        onClick={() => go(page)}
      >
        ← Назад
      </button>
    );
  }
  let content: ReactNode;
  if (loading) content = <p role="status">Загружаем сообщество…</p>;
  else if (!data)
    content = (
      <>
        <h1>Не удалось открыть сообщество</h1>
        <button
          className="button button-primary"
          onClick={() => {
            setLoading(true);
            setError("");
            void refresh()
              .catch((failure) => setError(failure.message))
              .finally(() => setLoading(false));
          }}
        >
          Повторить
        </button>
      </>
    );
  else if (screen === "materials")
    content = (
      <>
        <section className="community-welcome stack">
          <p className="eyebrow">СВОИ ЛЮДИ · НОВЫЕ ОТКРЫТИЯ</p>
          <h2>Быть внутри — интересно</h2>
          <p>
            Узнавай больше о компании, участвуй во встречах и собирай баллы на
            мерч.
          </p>
        </section>
        <Learning
          client={staffApi}
          onEarned={refresh}
          loadMedia={loadStaffMedia}
        />
      </>
    );
  else if (screen === "events")
    content = (
      <>
        <h1>Встречи команды</h1>
        <p className="muted">
          Выбирай событие, встречайся с коллегами и открывай активности на
          площадке.
        </p>
        <button className="button button-primary" onClick={() => go("scan")}>
          Сканировать QR-код
        </button>
        {data.events.length ? (
          data.events.map((event) => {
            const registered = data.registrations.some(
              (registration) =>
                registration.event === event.id &&
                registration.status !== "cancelled",
            );
            return (
              <button
                key={event.id}
                className="card card-click stack community-event-card"
                onClick={() => go("event", event.id)}
              >
                <p className="eyebrow">{event.type}</p>
                <h2>{event.title}</h2>
                <p className="small muted">
                  {date(event.date)} · {event.startTime} МСК
                </p>
                <p className="small muted">{event.location}</p>
                <p className="small">
                  {registered
                    ? "Ты записан ✓"
                    : eventStarted(event)
                      ? "Запись завершена"
                      : `Свободно ${event.remaining} мест`}
                </p>
                <span className="community-card-action">Подробнее →</span>
              </button>
            );
          })
        ) : (
          <Empty>Новые встречи команды скоро появятся здесь.</Empty>
        )}
      </>
    );
  else if (screen === "event") {
    const event = data.events.find((item) => item.id === id);
    const registered = data.registrations.some(
      (registration) =>
        registration.event === id && registration.status !== "cancelled",
    );
    content = event ? (
      <>
        {back()}
        <p className="eyebrow">{event.type}</p>
        <h1>{event.title}</h1>
        <div className="card stack">
          <p>
            {date(event.date)} · {event.startTime} МСК
          </p>
          <p>{event.location}</p>
          <p className="small muted">
            Свободно {event.remaining} из {event.capacity} мест
          </p>
        </div>
        <p>{event.description}</p>
        {event.program?.length ? (
          <section className="stack">
            <h2>Программа</h2>
            <ul className="community-list">
              {event.program.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}
        {event.requirements?.length ? (
          <section className="stack">
            <h2>Что нужно знать</h2>
            <ul className="community-list">
              {event.requirements.map((item, index) => (
                <li key={index}>{item}</li>
              ))}
            </ul>
          </section>
        ) : null}
        {registered ? (
          <>
            <p className="success" role="status">
              Ты записан на мероприятие
            </p>
            <button
              className="button button-secondary"
              disabled={busy}
              onClick={() =>
                void run(
                  `/events/${encodeURIComponent(event.id)}/registration`,
                  "DELETE",
                  "Запись отменена",
                )
              }
            >
              Отменить запись
            </button>
          </>
        ) : (
          <button
            className="button button-primary"
            disabled={busy || eventStarted(event) || event.remaining <= 0}
            onClick={() =>
              void run(
                `/events/${encodeURIComponent(event.id)}/registration`,
                "POST",
                "Ты записан на мероприятие",
              )
            }
          >
            {eventStarted(event)
              ? "Запись завершена"
              : event.remaining <= 0
                ? "Мест пока нет"
                : "Записаться"}
          </button>
        )}
        <EventActivities
          event={event}
          completions={data.activityCompletions}
          onScan={() => go("scan")}
        />
      </>
    ) : (
      <>
        {back()}
        <Empty>Мероприятие не найдено или недоступно этому аккаунту.</Empty>
      </>
    );
  } else if (screen === "scan")
    content = (
      <QrScanner
        onScan={scan}
        onBack={() => go("events")}
        onEvent={(eventId) => go("event", eventId)}
      />
    );
  else if (screen === "points")
    content = (
      <>
        <h1>Баллы и награды</h1>
        <section className="community-balance stack">
          <p className="eyebrow">ТВОЙ БАЛАНС</p>
          <strong>{data.balance} б.</strong>
          <p>За новые знания и участие в жизни команды.</p>
        </section>
        <div className="chips" aria-label="Баллы и награды">
          <button
            className={`chip ${pointsView === "rewards" ? "selected" : ""}`}
            aria-pressed={pointsView === "rewards"}
            onClick={() => setPointsView("rewards")}
          >
            Мерч
          </button>
          <button
            className={`chip ${pointsView === "history" ? "selected" : ""}`}
            aria-pressed={pointsView === "history"}
            onClick={() => setPointsView("history")}
          >
            История баллов
          </button>
        </div>
        {pointsView === "rewards" ? (
          <>
            <p className="small muted">
              Баллы за проверку знаний и активности поступают на один баланс.
              Каждая награда доступна для обмена один раз.
            </p>
            {data.rewards.length ? (
              data.rewards.map((reward) => (
                <RewardCard
                  key={reward.id}
                  reward={reward}
                  exchanged={data.exchanges.some(
                    (exchange) => exchange.reward === reward.id,
                  )}
                  onOpen={() => go("reward", reward.id)}
                />
              ))
            ) : (
              <Empty>Каталог мерча скоро появится здесь.</Empty>
            )}
          </>
        ) : data.ledger.length ? (
          <ul className="community-ledger">
            {data.ledger.map((entry) => (
              <li key={entry.id} className="card">
                <div className="row spread">
                  <strong>{ledgerTitle(entry, data)}</strong>
                  <span
                    className={entry.delta > 0 ? "community-credit" : "muted"}
                  >
                    {entry.delta > 0 ? "+" : ""}
                    {entry.delta} б.
                  </span>
                </div>
                <time className="small muted" dateTime={entry.created}>
                  {date(entry.created, true)} МСК
                </time>
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            Здесь появятся начисления за материалы и активности, а также обмены
            на мерч.
          </Empty>
        )}
      </>
    );
  else if (screen === "reward") {
    const reward = data.rewards.find((item) => item.id === id);
    const exchanged = data.exchanges.some((exchange) => exchange.reward === id);
    content = reward ? (
      <>
        {back("points")}
        <h1>{reward.title}</h1>
        <div className="community-reward-symbol" aria-hidden="true">
          ✦
        </div>
        <p>{reward.description}</p>
        <p>
          <strong>{reward.cost} баллов</strong> · Доступно {reward.remaining}
        </p>
        {exchanged ? (
          <p className="success" role="status">
            Обмен подтверждён. Уточни получение у организатора.
          </p>
        ) : (
          <>
            <p className="small muted">
              После подтверждения с баланса спишется {reward.cost} баллов.
              Получение мерча уточни у организатора.
            </p>
            <button
              className="button button-primary"
              disabled={
                busy || reward.remaining <= 0 || data.balance < reward.cost
              }
              onClick={() =>
                void run(
                  `/rewards/${encodeURIComponent(reward.id)}/exchange`,
                  "POST",
                  "Обмен подтверждён",
                )
              }
            >
              {reward.remaining <= 0
                ? "Награда закончилась"
                : data.balance < reward.cost
                  ? `Не хватает ${reward.cost - data.balance} баллов`
                  : `Обменять за ${reward.cost} баллов`}
            </button>
          </>
        )}
      </>
    ) : (
      <>
        {back("points")}
        <Empty>Награда не найдена.</Empty>
      </>
    );
  } else if (screen === "referral" && role === "intern")
    content = (
      <>
        <h1>Приведи друга</h1>
        <ReferralCard client={staffApi} />
      </>
    );
  else
    content = (
      <>
        <h1>Раздел не найден</h1>
        <button
          className="button button-primary"
          onClick={() => go("materials")}
        >
          К материалам
        </button>
      </>
    );
  const active = ["event", "scan"].includes(screen)
    ? "events"
    : screen === "reward"
      ? "points"
      : screen;
  const tabs = [
    ["materials", "◇", "Материалы"],
    ["events", "▦", "События"],
    ["points", "✦", "Мерч"],
  ];
  if (role === "intern") tabs.push(["referral", "♡", "Приведи друга"]);
  return (
    <div className="app-shell community-shell">
      <header className="app-header community-header">
        <a className="brand" href={`#/${root}/materials`}>
          Очаково: изнутри
        </a>
        <button
          className="balance-pill"
          aria-label={`Мои баллы: ${data?.balance ?? 0}`}
          onClick={() => go("points")}
        >
          {data?.balance ?? 0} б.
        </button>
        <button className="community-logout" onClick={() => void onLogout()}>
          Выйти
        </button>
      </header>
      <main
        className="screen stack community-content"
        ref={heading}
        tabIndex={-1}
      >
        <div className="community-section-heading">
          <p className="eyebrow">СООБЩЕСТВО ОЧАКОВО</p>
          {role !== "employee" && (
            <a
              className="small community-card-action"
              href={`#/${staffHome(role)}`}
            >
              {role === "mentor" ? "К практике наставника" : "К моей практике"}{" "}
              →
            </a>
          )}
        </div>
        {error && (
          <div className="error" role="alert">
            {error}
            <button
              type="button"
              className="button-ghost"
              aria-label="Закрыть ошибку"
              onClick={() => setError("")}
            >
              ×
            </button>
          </div>
        )}
        {content}
      </main>
      <nav className="bottom-nav" aria-label="Сообщество сотрудников">
        {tabs.map(([key, icon, label]) => (
          <button
            key={key}
            className={`nav-item ${active === key ? "active" : ""}`}
            aria-current={active === key ? "page" : undefined}
            onClick={() => go(key)}
          >
            <span aria-hidden="true">{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </nav>
      {notice && (
        <div className="toast" role="status">
          {notice}
        </div>
      )}
    </div>
  );
}

function RewardCard({
  reward,
  exchanged,
  onOpen,
}: {
  reward: Reward;
  exchanged: boolean;
  onOpen: () => void;
}) {
  return (
    <button className="card card-click stack" onClick={onOpen}>
      <p className="eyebrow">МЕРЧ ОЧАКОВО</p>
      <h2>{reward.title}</h2>
      <p className="small muted">{reward.description}</p>
      <span className="community-card-action">
        {exchanged
          ? "Обмен подтверждён ✓"
          : `${reward.cost} баллов · Подробнее →`}
      </span>
    </button>
  );
}
