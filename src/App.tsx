import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, initialize, requestNotifications } from "./api";
import { GamePlayer } from "./games/Games";
import type { Task, CompletionResult } from "./games/types";
import { Mascot, WelcomeHistory } from "./components/Art";
import { nextDraftRevision, syncDraftClock } from "./draftClock";
import { localStore, sessionStore } from "./storage";
import {
  DIRECTIONS,
  STATUSES,
  type Bootstrap,
  type Profile,
  type Offer,
  type CareerEvent,
  type Reward,
  type Application,
} from "./types";

type Route = { page: string; id?: string };
function readRoute(): Route {
  const [page, id] = location.hash.replace(/^#\/?/, "").split("/");
  return { page: page || "home", id };
}
function navigate(page: string, id?: string) {
  location.hash = "/" + page + (id ? "/" + encodeURIComponent(id) : "");
}
const date = (value: string) =>
  new Date(
    value.length === 10 ? value + "T12:00:00+03:00" : value,
  ).toLocaleDateString("ru-RU", {
    timeZone: "Europe/Moscow",
    day: "numeric",
    month: "long",
  });
const emptyProfile: Profile = {
  fullName: "",
  contact: "",
  birthDate: "",
  direction: "undecided",
  availability: "",
  education: "",
  schedule: "",
  consent: false,
  futureContact: false,
};
const gameLabels: Record<string, string> = {
  signal: "Алгоритм",
  movement: "Конструктор",
  lab: "Исследование",
  delivery: "Комплектация",
  history: "История и бренды",
};
const gameNumbers: Record<string, string> = {
  signal: "02",
  movement: "03",
  lab: "04",
  delivery: "05",
  history: "06",
};

function Button({
  children,
  secondary,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { secondary?: boolean }) {
  return (
    <button
      {...props}
      className={`button ${secondary ? "button-secondary" : "button-primary"} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}
function DemoTag() {
  return <span className="tag tag-demo">Демонстрация</span>;
}
function Back({
  page = "home",
  children = "Назад",
}: {
  page?: string;
  children?: ReactNode;
}) {
  return (
    <button
      type="button"
      className="button-ghost back-link"
      onClick={() => navigate(page)}
    >
      ← {children}
    </button>
  );
}
function Empty({ children }: React.PropsWithChildren) {
  return (
    <div className="empty card">
      <p>{children}</p>
    </div>
  );
}
function CardLink({
  icon,
  title,
  children,
  onClick,
  dark = false,
}: React.PropsWithChildren<{
  icon: string;
  title: string;
  onClick: () => void;
  dark?: boolean;
}>) {
  return (
    <button
      className={`card card-click row ${dark ? "card-dark" : ""}`}
      onClick={onClick}
    >
      <span className="card-icon" aria-hidden="true">
        {icon}
      </span>
      <span className="card-copy stack">
        <strong>{title}</strong>
        <span className="small muted">{children}</span>
      </span>
      <span aria-hidden="true">↗</span>
    </button>
  );
}

export default function App() {
  const [data, setData] = useState<Bootstrap | null>(null);
  const [route, setRoute] = useState<Route>(readRoute);
  const [mode, setMode] = useState("");
  const [vkName, setVkName] = useState("");
  const [started, setStarted] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [confirm, setConfirm] = useState<{
    title: string;
    body: ReactNode;
    label: string;
    action: () => Promise<void>;
  } | null>(null);
  const [rewardGoal, setRewardGoal] = useState("");
  const headingRef = useRef<HTMLElement>(null);
  const refresh = useCallback(async () => {
    const next = await api<Bootstrap>("/bootstrap");
    syncDraftClock(
      next.progress.map((p) => p.revision ?? p.draft_revision ?? 0),
    );
    setData(next);
    return next;
  }, []);
  const start = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const result = await initialize();
      setData(result.data);
      setMode(result.mode);
      setVkName(result.vkName ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось подключиться.");
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void start();
  }, [start]);
  useEffect(() => {
    const changed = () => {
      setRoute(readRoute());
      setError("");
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    if (toast) {
      const timeout = setTimeout(() => setToast(""), 4500);
      return () => clearTimeout(timeout);
    }
  }, [toast]);
  useEffect(() => {
    if (data?.userId || data?.user?.id)
      setRewardGoal(
        localStore.get(`ochakovo:goal:${data.userId ?? data.user?.id}`) ?? "",
      );
  }, [data?.userId, data?.user?.id]);
  useEffect(() => {
    headingRef.current?.focus({ preventScroll: true });
  }, [route.page, route.id]);
  useEffect(() => {
    if (!data) return;
    const name = (
      {
        game: "task_opened",
        offer: "offer_viewed",
        event: "event_viewed",
        reward: "reward_viewed",
      } as Record<string, string>
    )[route.page];
    if (name)
      void api("/analytics", "POST", { event: name }).catch(() => undefined);
  }, [route.page, route.id, Boolean(data)]);
  async function act(action: () => Promise<void>, message?: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
      setConfirm(null);
      if (message) setToast(message);
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Не удалось сохранить. Попробуй ещё раз.",
      );
    } finally {
      setBusy(false);
    }
  }
  function goal(reward: Reward) {
    setRewardGoal(reward.id);
    localStore.set(
      `ochakovo:goal:${data?.userId ?? data?.user?.id}`,
      reward.id,
    );
    setToast("Цель сохранена");
  }
  const profile = data?.profile;
  const catalog = data?.catalog;
  const progress = data?.progress ?? [];
  const page = route.page;
  const privacy = page === "privacy";

  if (page === "admin") return <Admin />;
  if (loading)
    return (
      <main className="app-shell screen loading" aria-busy="true">
        <span className="loading-mark" aria-hidden="true">
          О
        </span>
        <p>Открываем вкус к делу…</p>
      </main>
    );
  if (!data || !catalog)
    return (
      <main className="app-shell screen stack">
        <p className="eyebrow">ОЧАКОВО: ИЗНУТРИ</p>
        <h1 className="page-title">Не удалось подключиться</h1>
        <p role="alert" className="error">
          {error}
        </p>
        <p className="muted">
          Открой приложение внутри VK. Для локальной демонстрации запусти проект
          командой npm run dev.
        </p>
        <Button onClick={() => void start()}>Попробовать снова</Button>
      </main>
    );
  if (privacy)
    return (
      <div className="app-shell">
        <main className="screen stack">
          <Back page={profile ? "profile" : "home"} />
          <Privacy />
        </main>
      </div>
    );
  if (!profile) {
    if (!started)
      return (
        <main className="app-shell welcome stack">
          <p className="brand">Очаково: изнутри</p>
          <p className="eyebrow">ОТКРЫВАЕМ</p>
          <h1 className="welcome-title">
            ВКУС
            <br />К ДЕЛУ
          </h1>
          <div className="welcome-mascot row">
            <Mascot />
            <h2>
              Открой,
              <br />
              что тебе
              <br />
              по вкусу.
            </h2>
          </div>
          <p>
            Твоя первая встреча с профессиями, людьми и возможностями Очаково.
          </p>
          <Button secondary onClick={() => setStarted(true)}>
            Открыть свой маршрут
          </Button>
          <p className="small">Играй · узнавай компанию · выбирай практику</p>
          <WelcomeHistory />
        </main>
      );
    return (
      <div className="app-shell">
        <main className="screen">
          <ProfileForm
            initial={{ ...emptyProfile, fullName: vkName }}
            demo={mode === "demo"}
            busy={busy}
            error={error}
            onBack={() => setStarted(false)}
            onSave={(p) =>
              act(async () => {
                await api("/profile", "PUT", p);
                navigate("home");
              }, "Профиль сохранён")
            }
          />
        </main>
      </div>
    );
  }
  const activeTab = ["tasks", "game"].includes(page)
    ? "tasks"
    : ["career", "offer", "applications"].includes(page)
      ? "career"
      : ["events", "event", "registrations"].includes(page)
        ? "events"
        : "home";
  const task = catalog.tasks.find((t) => t.id === route.id);
  const offer = catalog.offers.find((o) => o.id === route.id);
  const event = catalog.events.find((e) => e.id === route.id);
  const reward = catalog.rewards.find((r) => r.id === route.id);
  const ongoing = progress.find(
    (p) => !p.completed && p.draft && Object.keys(p.draft as object).length,
  );
  const continueTask =
    catalog.tasks.find((t) => t.id === ongoing?.task) ??
    catalog.tasks.find(
      (t) => !progress.some((p) => p.task === t.id && p.completed),
    );
  const relevantOffers = catalog.offers.filter(
    (o) =>
      profile.direction === "undecided" || o.direction === profile.direction,
  );
  const upcoming = catalog.events
    .filter(
      (e) =>
        new Date(`${e.date}T${e.startTime || "12:00"}:00+03:00`) > new Date(),
    )
    .sort((a, b) => a.date.localeCompare(b.date))[0];
  let content: ReactNode;

  switch (page) {
    case "home":
      content = (
        <>
          <section className="hero stack">
            <p className="eyebrow">ОТКРЫВАЕМ ВКУС К ДЕЛУ</p>
            <div className="hero-row row">
              <div className="hero-copy stack">
                <h1>
                  ТВОЁ ДЕЛО
                  <br />
                  НАЧИНАЕТСЯ
                  <br />
                  ЗДЕСЬ
                </h1>
                <p className="small">Пять способов попробовать профессию.</p>
              </div>
              <Mascot />
            </div>
          </section>
          <Button onClick={() => navigate("tasks")}>Выбрать задание</Button>
          {data.routeCompleted && (
            <div className="success stack">
              <h2>Маршрут открыт!</h2>
              <p>
                Ты попробовал четыре профессии и познакомился с историей.
                Следующий шаг — встреча с командой.
              </p>
              <button
                className="button-ghost"
                onClick={() => navigate("events")}
              >
                Выбрать экскурсию →
              </button>
            </div>
          )}
          {continueTask && (
            <CardLink
              icon={gameNumbers[continueTask.game] ?? "02"}
              title={ongoing ? "Продолжим?" : "Откроем, как это работает?"}
              dark
              onClick={() => navigate("game", continueTask.id)}
            >
              {continueTask.title} · +{continueTask.points} баллов
            </CardLink>
          )}
          <CardLink
            icon="→"
            title="Открой свою практику"
            onClick={() => navigate("career")}
          >
            Задачи и условия карьерного старта
          </CardLink>
          <CardLink
            icon="↗"
            title="Встретимся вживую"
            onClick={() => navigate("events")}
          >
            Экскурсии и карьерные встречи
          </CardLink>
          {relevantOffers.length > 0 && (
            <section className="stack">
              <h2 className="section-title">По твоим интересам</h2>
              <OfferCard
                offer={relevantOffers[0]}
                applied={data.applications.some(
                  (a) => a.offer === relevantOffers[0].id,
                )}
              />
              <button
                className="button-ghost"
                onClick={() => navigate("profile")}
              >
                Изменить направление →
              </button>
            </section>
          )}
          {upcoming && (
            <p className="small muted">
              Ближайшая встреча: {date(upcoming.date)} · {upcoming.title}
            </p>
          )}
        </>
      );
      break;
    case "tasks":
      content = <Tasks tasks={catalog.tasks} progress={progress} />;
      break;
    case "game":
      content = task ? (
        <GamePlayer
          key={task.id}
          task={task}
          draft={progress.find((p) => p.task === task.id)?.draft}
          onSave={async (draft, requestedRevision) => {
            const revision = requestedRevision ?? nextDraftRevision();
            setData((current) => {
              if (!current) return current;
              const previous = current.progress.find((p) => p.task === task.id);
              if (
                (previous?.revision ?? previous?.draft_revision ?? 0) > revision
              )
                return current;
              return {
                ...current,
                progress: [
                  ...current.progress.filter((p) => p.task !== task.id),
                  {
                    task: task.id,
                    draft,
                    revision,
                    completed: previous?.completed ?? null,
                  },
                ],
              };
            });
            try {
              await api(`/tasks/${task.id}/draft`, "PUT", { draft, revision });
            } catch (e) {
              setToast(
                "Прогресс не сохранён на сервере. Вернись в задание и повтори сохранение.",
              );
              throw e;
            }
          }}
          onComplete={async (solution) => {
            const result = await api<CompletionResult>(
              `/tasks/${task.id}/complete`,
              "POST",
              { solution },
            );
            await refresh();
            return result;
          }}
          onCareer={(direction) => {
            navigate("career");
            sessionStore.set("ochakovo:career-direction", direction);
          }}
          onExit={() => {
            void refresh();
            navigate("tasks");
          }}
        />
      ) : (
        <Empty>
          Такое задание не найдено.{" "}
          <button className="button-ghost" onClick={() => navigate("tasks")}>
            К заданиям
          </button>
        </Empty>
      );
      break;
    case "career":
      content = (
        <Career
          offers={catalog.offers}
          applications={data.applications}
          direction={profile.direction}
        />
      );
      break;
    case "offer":
      content = offer ? (
        <OfferDetail
          offer={offer}
          profile={profile}
          application={data.applications.find((a) => a.offer === offer.id)}
          onApply={() =>
            setConfirm({
              title: "Отправить отклик?",
              body: (
                <div className="stack">
                  <p>
                    <strong>{offer.title}</strong>
                  </p>
                  <ProfileSummary profile={profile} />
                  <p className="small muted">
                    Демонстрационная заявка сохранится в приложении и будет
                    доступна в кабинете HR. Баллы за отклик не начисляются.
                  </p>
                </div>
              ),
              label: "Подтвердить отправку",
              action: () =>
                act(async () => {
                  await api("/applications", "POST", { offerId: offer.id });
                  navigate("applications");
                }, "Отклик получен приложением"),
            })
          }
        />
      ) : (
        <Empty>Предложение не найдено.</Empty>
      );
      break;
    case "applications":
      content = (
        <>
          <Back page="career" />
          <h1 className="page-title">Мои отклики</h1>
          <p className="muted">
            Статусы сохранённых заявок. Это демонстрация, ответы компании не
            имитируются.
          </p>
          {data.applications.length ? (
            data.applications.map((a) => (
              <article className="card stack" key={a.id}>
                <p className="eyebrow">{STATUSES[a.status] ?? a.status}</p>
                <h2>
                  {catalog.offers.find((o) => o.id === a.offer)?.title ??
                    a.offer}
                </h2>
                <p className="small muted">
                  Отправлен {date(a.created)} · № {a.id.slice(0, 8)}
                </p>
                <button
                  className="button-ghost"
                  onClick={() => navigate("offer", a.offer)}
                >
                  Посмотреть предложение →
                </button>
              </article>
            ))
          ) : (
            <Empty>
              Пока нет откликов. Выбери практику или вакансию в разделе
              «Карьера».
            </Empty>
          )}
        </>
      );
      break;
    case "events":
      content = (
        <Events events={catalog.events} registrations={data.registrations} />
      );
      break;
    case "event": {
      const registration = data.registrations.find(
        (r) => r.event === event?.id && r.status !== "cancelled",
      );
      content = event ? (
        <>
          <Back page="events" />
          <div className="row spread">
            <p className="eyebrow">{event.type}</p>
            <DemoTag />
          </div>
          <h1 className="page-title">{event.title}</h1>
          <p>{event.description}</p>
          <div className="card stack">
            <p>
              <strong>
                {date(event.date)} · {event.startTime} МСК
              </strong>
            </p>
            <p>{event.location}</p>
            <p className="small muted">
              Свободно мест: {event.remaining} из {event.capacity}
            </p>
            {event.program?.length ? (
              <ul>
                {event.program.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : null}
            {event.requirements?.length ? (
              <ul>
                {event.requirements.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : (
              <p className="small muted">
                Запись по профилю. Программа и условия уточняются перед пилотом.
              </p>
            )}
          </div>
          {registration ? (
            <>
              <p className="success" role="status">
                Ты записан. № {registration.id.slice(0, 8)}
              </p>
              <Button
                secondary
                onClick={() =>
                  setConfirm({
                    title: "Отменить участие?",
                    body: <p>Место снова станет доступно другим участникам.</p>,
                    label: "Отменить запись",
                    action: () =>
                      act(async () => {
                        await api(`/events/${event.id}/registration`, "DELETE");
                      }, "Запись отменена"),
                  })
                }
              >
                Отменить запись
              </Button>
            </>
          ) : (
            <Button
              disabled={
                event.remaining <= 0 ||
                new Date(`${event.date}T${event.startTime}:00+03:00`) <=
                  new Date()
              }
              onClick={() =>
                setConfirm({
                  title: "Подтвердить запись",
                  body: (
                    <div className="stack">
                      <p>
                        {event.title} · {date(event.date)}
                      </p>
                      <ProfileSummary profile={profile} />
                      <p className="small muted">
                        Это демонстрационная запись; она не является реальным
                        приглашением на предприятие.
                      </p>
                    </div>
                  ),
                  label: "Записаться с моим профилем",
                  action: () =>
                    act(async () => {
                      await api(`/events/${event.id}/registration`, "POST", {});
                      navigate("registrations");
                    }, "Запись сохранена"),
                })
              }
            >
              {event.remaining > 0 ? "Записаться" : "Мест пока нет"}
            </Button>
          )}
          <button
            className="button-ghost"
            onClick={() => navigate("registrations")}
          >
            Мои записи →
          </button>
        </>
      ) : (
        <Empty>Событие не найдено.</Empty>
      );
      break;
    }
    case "registrations":
      content = (
        <>
          <Back page="events" />
          <h1 className="page-title">Мои записи</h1>
          {data.registrations.length ? (
            data.registrations.map((r) => {
              const e = catalog.events.find((e) => e.id === r.event);
              return (
                <article className="card stack" key={r.id}>
                  <span className="eyebrow">
                    {STATUSES[r.status] ?? r.status}
                  </span>
                  <h2>{e?.title ?? r.event}</h2>
                  <p>{e && `${date(e.date)} · ${e.startTime} МСК`}</p>
                  <p className="small muted">
                    № {r.id.slice(0, 8)} · Демонстрационная запись
                  </p>
                  <button
                    className="button-ghost"
                    onClick={() => navigate("event", r.event)}
                  >
                    Детали и отмена →
                  </button>
                </article>
              );
            })
          ) : (
            <Empty>Твои встречи появятся здесь после записи.</Empty>
          )}
        </>
      );
      break;
    case "points":
      content = <Points data={data} goal={rewardGoal} />;
      break;
    case "reward": {
      const exchanged = data.exchanges.find((e) => e.reward === reward?.id);
      content = reward ? (
        <>
          <Back page="points" />
          <p className="eyebrow">КАТАЛОГ НАГРАД</p>
          <h1 className="page-title">{reward.title}</h1>
          <div className="row spread">
            <strong className="page-title">{reward.cost} б.</strong>
            <DemoTag />
          </div>
          <p>{reward.description}</p>
          <p className="small muted">
            Осталось: {reward.remaining}. Ассортимент и выдача требуют
            согласования с компанией.
          </p>
          {exchanged ? (
            <div className="success">
              Обмен сохранён · № {exchanged.id.slice(0, 8)}. Это
              демонстрационный обмен; фактическая выдача не запланирована.
            </div>
          ) : (
            <Button
              disabled={data.balance < reward.cost || reward.remaining <= 0}
              onClick={() =>
                setConfirm({
                  title: `Обменять ${reward.cost} баллов?`,
                  body: (
                    <p>
                      «{reward.title}» появится в истории обменов. Каталог
                      демонстрационный, реальная выдача награды не обещается.
                    </p>
                  ),
                  label: "Подтвердить обмен",
                  action: () =>
                    act(async () => {
                      await api(`/rewards/${reward.id}/exchange`, "POST", {});
                    }, "Обмен сохранён"),
                })
              }
            >
              {data.balance < reward.cost
                ? `Ещё ${reward.cost - data.balance} б. до награды`
                : reward.remaining <= 0
                  ? "Закончилась"
                  : "Обменять баллы"}
            </Button>
          )}
          <Button secondary onClick={() => goal(reward)}>
            {rewardGoal === reward.id ? "Это моя цель ✓" : "Выбрать целью"}
          </Button>
          <button className="button-ghost" onClick={() => navigate("tasks")}>
            Открыть задания →
          </button>
        </>
      ) : (
        <Empty>Награда не найдена.</Empty>
      );
      break;
    }
    case "profile":
      content = (
        <>
          <Back />
          <h1 className="page-title">Мой профиль</h1>
          <ProfileSummary profile={profile} />
          <CardLink
            icon="→"
            title="Мои отклики"
            onClick={() => navigate("applications")}
          >
            {data.applications.length} отправлено
          </CardLink>
          <CardLink
            icon="↗"
            title="Мои записи"
            onClick={() => navigate("registrations")}
          >
            {data.registrations.filter((r) => r.status !== "cancelled").length}{" "}
            активных
          </CardLink>
          <CardLink
            icon="◇"
            title="Мой прогресс"
            onClick={() => navigate("tasks")}
          >
            {progress.filter((p) => p.completed).length} уровней завершено
          </CardLink>
          <Button secondary onClick={() => navigate("edit-profile")}>
            Редактировать профиль
          </Button>
          <button
            className="button-ghost"
            onClick={() =>
              void act(async () => {
                await requestNotifications();
              }, "Уведомления включены")
            }
          >
            Разрешить уведомления VK
          </button>
          <button className="button-ghost" onClick={() => navigate("privacy")}>
            Данные и согласия →
          </button>
          <p className="small muted">
            {mode === "demo"
              ? "Локальная демонстрация. Используй вымышленные данные."
              : "Профиль привязан к твоему аккаунту VK."}
          </p>
        </>
      );
      break;
    case "edit-profile":
      content = (
        <ProfileForm
          initial={profile}
          demo={mode === "demo"}
          busy={busy}
          error=""
          onBack={() => navigate("profile")}
          onSave={(p) =>
            act(async () => {
              await api("/profile", "PUT", p);
              navigate("profile");
            }, "Профиль обновлён")
          }
        />
      );
      break;
    default:
      content = (
        <>
          <h1>Экран не найден</h1>
          <Button onClick={() => navigate("home")}>На главную</Button>
        </>
      );
  }
  return (
    <div className="app-shell">
      <header className="app-header row spread">
        <button className="brand button-ghost" onClick={() => navigate("home")}>
          Очаково: изнутри
        </button>
        <div className="header-actions row">
          <button
            aria-label={`Мои баллы: ${data.balance}`}
            className="balance-pill"
            onClick={() => navigate("points")}
          >
            {data.balance} б.
          </button>
          <button
            className="avatar"
            aria-label="Мой профиль"
            onClick={() => navigate("profile")}
          >
            {profile.fullName.slice(0, 1)}
          </button>
        </div>
      </header>
      <main className="screen stack" ref={headingRef} tabIndex={-1}>
        {error && (
          <div className="error" role="alert">
            {error}
            <button
              className="button-ghost"
              onClick={() => setError("")}
              aria-label="Закрыть ошибку"
            >
              ×
            </button>
          </div>
        )}
        {content}
      </main>
      <nav className="bottom-nav" aria-label="Основная навигация">
        {[
          ["home", "⌂", "Для тебя"],
          ["tasks", "◇", "Задания"],
          ["career", "▣", "Карьера"],
          ["events", "▦", "События"],
        ].map(([key, icon, title]) => (
          <button
            key={key}
            className={`nav-item ${activeTab === key ? "active" : ""}`}
            aria-current={activeTab === key ? "page" : undefined}
            onClick={() => navigate(key)}
          >
            <span aria-hidden="true">{icon}</span>
            <span>{title}</span>
          </button>
        ))}
      </nav>
      {toast && (
        <div role="status" className="toast">
          {toast}
        </div>
      )}
      {confirm && (
        <Modal
          title={confirm.title}
          busy={busy}
          onClose={() => {
            if (!busy) {
              setConfirm(null);
              setError("");
            }
          }}
        >
          {confirm.body}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <Button disabled={busy} onClick={() => void confirm.action()}>
            {busy ? "Сохраняем…" : confirm.label}
          </Button>
        </Modal>
      )}
    </div>
  );
}

function ProfileSummary({ profile }: { profile: Profile }) {
  return (
    <dl className="profile-summary card detail-list">
      <div>
        <dt>ФИО</dt>
        <dd>{profile.fullName}</dd>
      </div>
      <div>
        <dt>Для связи</dt>
        <dd>{profile.contact}</dd>
      </div>
      <div>
        <dt>Образование</dt>
        <dd>{profile.education}</dd>
      </div>
      <div>
        <dt>Интерес</dt>
        <dd>{DIRECTIONS[profile.direction] ?? profile.direction}</dd>
      </div>
      <div>
        <dt>Готовность выйти</dt>
        <dd>{profile.availability}</dd>
      </div>
      {profile.schedule && (
        <div>
          <dt>График</dt>
          <dd>{profile.schedule}</dd>
        </div>
      )}
    </dl>
  );
}

function ProfileForm({
  initial,
  demo,
  busy,
  error,
  onBack,
  onSave,
}: {
  initial: Profile;
  demo: boolean;
  busy: boolean;
  error: string;
  onBack: () => void;
  onSave: (profile: Profile) => Promise<void>;
}) {
  const [value, setValue] = useState(initial);
  const [step, setStep] = useState(1);
  const [validation, setValidation] = useState("");
  const set = (field: keyof Profile, fieldValue: string | boolean) =>
    setValue((v) => ({ ...v, [field]: fieldValue }));
  function submit(e: FormEvent) {
    e.preventDefault();
    setValidation("");
    if (step === 1) {
      if (value.fullName.trim().split(/\s+/).length < 2) {
        setValidation("Укажи имя и фамилию.");
        return;
      }
      const today = new Intl.DateTimeFormat("sv-SE", {
        timeZone: "Europe/Moscow",
      }).format(new Date());
      const age =
        Number(today.slice(0, 4)) -
        Number(value.birthDate.slice(0, 4)) -
        (today.slice(5) < value.birthDate.slice(5) ? 1 : 0);
      if (!Number.isFinite(age) || age < 18 || age > 100) {
        setValidation(
          "Приложение рассчитано на участников от 18 лет. Проверь дату рождения.",
        );
        return;
      }
      if (
        !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.contact.trim()) &&
        !(
          /^[+\d\s()\-]+$/.test(value.contact.trim()) &&
          value.contact.replace(/\D/g, "").length >= 10 &&
          value.contact.replace(/\D/g, "").length <= 15
        )
      ) {
        setValidation("Укажи корректный телефон или электронную почту.");
        return;
      }
      setStep(2);
      window.scrollTo(0, 0);
      return;
    }
    void onSave({
      ...value,
      fullName: value.fullName.trim(),
      contact: value.contact.trim(),
      education: value.education.trim(),
    });
  }
  return (
    <form className="stack" onSubmit={submit}>
      <button
        type="button"
        className="button-ghost back-link"
        onClick={() => (step === 2 ? setStep(1) : onBack())}
      >
        ← Назад
      </button>
      <p className="brand">Очаково: изнутри</p>
      <p className="eyebrow">ШАГ {step} ИЗ 2</p>
      <h1 className="page-title">
        {step === 1 ? "Давай познакомимся" : "Что тебе по вкусу?"}
      </h1>
      <p className="muted">
        {step === 1
          ? "Профиль нужен для подбора направлений и откликов без повторной анкеты."
          : "Выбери интерес и расскажи, когда готов начать. Направление можно изменить."}
      </p>
      {step === 1 ? (
        <>
          <label className="field">
            ФИО
            <input
              className="form-input"
              autoComplete="name"
              required
              maxLength={160}
              value={value.fullName}
              onChange={(e) => set("fullName", e.target.value)}
              placeholder="Как к тебе обращаться"
            />
          </label>
          <label className="field">
            Дата рождения
            <input
              className="form-input"
              type="date"
              required
              value={value.birthDate}
              onChange={(e) => set("birthDate", e.target.value)}
            />
          </label>
          <label className="field">
            Контакт для связи
            <input
              className="form-input"
              autoComplete="email"
              required
              maxLength={180}
              value={value.contact}
              onChange={(e) => set("contact", e.target.value)}
              placeholder="Телефон или электронная почта"
            />
          </label>
        </>
      ) : (
        <>
          <label className="field">
            Интересующее направление
            <select
              className="form-select"
              value={value.direction}
              onChange={(e) => set("direction", e.target.value)}
            >
              {Object.entries(DIRECTIONS).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Вуз или колледж
            <input
              className="form-input"
              required
              maxLength={200}
              value={value.education}
              onChange={(e) => set("education", e.target.value)}
              placeholder="Учебное заведение или «Уже окончил»"
            />
          </label>
          <label className="field">
            Готовность выйти
            <select
              className="form-select"
              required
              value={value.availability}
              onChange={(e) => set("availability", e.target.value)}
            >
              <option value="">Выбери вариант</option>
              {[
                "В ближайшие две недели",
                "Через месяц",
                "На время практики",
                "На летний сезон",
                "Пока знакомлюсь",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="field">
            Предпочтительный график
            <select
              className="form-select"
              value={value.schedule}
              onChange={(e) => set("schedule", e.target.value)}
            >
              <option value="">Готов обсудить</option>
              {[
                "Совмещать с учёбой",
                "Полная занятость",
                "Сменный график",
                "Сезонная работа",
              ].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="check">
            <input
              type="checkbox"
              required
              checked={value.consent}
              onChange={(e) => set("consent", e.target.checked)}
            />
            <span>
              Согласен на обработку данных профиля и заявок в рамках этой
              демонстрации.
            </span>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={value.futureContact}
              onChange={(e) => set("futureContact", e.target.checked)}
            />
            <span>
              Можно связаться со мной по будущим предложениям — необязательно.
            </span>
          </label>
        </>
      )}
      {validation || error ? (
        <p className="error" role="alert">
          {validation || error}
        </p>
      ) : null}
      <a className="small muted" href="#/privacy">
        Как используются данные →
      </a>
      <Button disabled={busy} type="submit">
        {busy ? "Сохраняем…" : step === 1 ? "Продолжить" : "Сохранить профиль"}
      </Button>
      {demo && (
        <p className="small muted">
          Демонстрация. Используй вымышленные данные. Профиль не является
          откликом.
        </p>
      )}
    </form>
  );
}

function Tasks({
  tasks,
  progress,
}: {
  tasks: Task[];
  progress: Bootstrap["progress"];
}) {
  const [topic, setTopic] = useState("all");
  const [state, setState] = useState("all");
  const visibleTasks = tasks.filter((task) => {
    if (topic === "history" && task.game !== "history") return false;
    if (topic === "professions" && task.game === "history") return false;
    const item = progress.find((p) => p.task === task.id);
    return (
      state === "all" ||
      (state === "completed"
        ? Boolean(item?.completed)
        : state === "started"
          ? Boolean(item && !item.completed)
          : !item)
    );
  });
  const groups = [...new Set(visibleTasks.map((t) => t.game))];
  return (
    <>
      <p className="eyebrow">ПОПРОБУЙ ПРОФЕССИЮ</p>
      <h1 className="page-title">
        У каждого вкуса
        <br />
        есть команда
      </h1>
      <p className="muted">
        Собирай, исследуй, открывай новое. Найди дело, которое тебе по вкусу.
      </p>
      <div className="chips" aria-label="Темы заданий">
        {[
          ["all", "Все"],
          ["professions", "Профессии"],
          ["history", "История и бренды"],
        ].map(([id, title]) => (
          <button
            key={id}
            className={`chip ${topic === id ? "selected" : ""}`}
            onClick={() => setTopic(id)}
          >
            {title}
          </button>
        ))}
      </div>
      <label className="field">
        Показывать
        <select
          className="form-select"
          value={state}
          onChange={(e) => setState(e.target.value)}
        >
          {[
            ["all", "Все задания"],
            ["new", "Новые"],
            ["started", "Начатые"],
            ["completed", "Пройденные"],
          ].map(([id, title]) => (
            <option key={id} value={id}>
              {title}
            </option>
          ))}
        </select>
      </label>
      {topic !== "history" && state === "all" && (
        <article
          className="card task-card task-unavailable"
          aria-label="Разберись в смене — скоро"
        >
          <span className="task-number">01</span>
          <div className="task-info stack">
            <p className="eyebrow">СИМУЛЯТОР · СКОРО</p>
            <h2>Разберись в смене</h2>
            <p className="small muted">
              Новые экраны и механика появятся позже.
            </p>
          </div>
        </article>
      )}
      {!visibleTasks.length && (
        <Empty>
          Заданий с такими условиями пока нет. Измени фильтр, чтобы увидеть
          другие уровни.
        </Empty>
      )}
      {groups
        .filter(
          (g) =>
            topic === "all" ||
            (topic === "history" ? g === "history" : g !== "history"),
        )
        .map((game) => {
          const levels = tasks.filter((t) => t.game === game);
          const visible = visibleTasks.filter((t) => t.game === game);
          if (!visible.length) return null;
          const done = levels.filter((t) =>
            progress.some((p) => p.task === t.id && p.completed),
          ).length;
          return (
            <section className="card stack" key={game}>
              <div className="row">
                <span className="task-number">{gameNumbers[game]}</span>
                <div className="stack task-info">
                  <p className="eyebrow">{gameLabels[game]}</p>
                  <h2>{levels[0].title}</h2>
                </div>
              </div>
              <p className="small muted">{levels[0].description}</p>
              <div className="row spread small">
                <span>{levels[0].duration}</span>
                <span>до +{levels[0].points} б. за уровень</span>
              </div>
              <div className="chips">
                {visible.map((t) => (
                  <button
                    className={`chip ${progress.some((p) => p.task === t.id && p.completed) ? "selected" : ""}`}
                    onClick={() => navigate("game", t.id)}
                    key={t.id}
                  >
                    {t.game === "history"
                      ? "Открыть тест"
                      : `Уровень ${t.level}`}{" "}
                    {progress.some((p) => p.task === t.id && p.completed)
                      ? "✓"
                      : "→"}
                  </button>
                ))}
              </div>
              <span className="small muted">
                Пройдено: {done} из {levels.length}
              </span>
            </section>
          );
        })}
      <p className="small muted">
        Повтор улучшает результат, но баллы за уже пройденный уровень не
        начисляются повторно. Учебные игры не оценивают квалификацию.
      </p>
    </>
  );
}

function OfferCard({ offer, applied }: { offer: Offer; applied?: boolean }) {
  return (
    <button
      className="card card-click stack"
      onClick={() => navigate("offer", offer.id)}
    >
      <div className="row spread">
        <span className="eyebrow">{offer.type}</span>
        <DemoTag />
      </div>
      <h2>{offer.title}</h2>
      <p className="small muted">{offer.location}</p>
      <p className="small">{offer.schedule}</p>
      <p className="small muted">{offer.pay}</p>
      <span className="tag tag-red">
        {applied ? "Отклик отправлен ✓" : "Задачи и условия →"}
      </span>
    </button>
  );
}
function Career({
  offers,
  applications,
  direction,
}: {
  offers: Offer[];
  applications: Application[];
  direction: string;
}) {
  const [filter, setFilter] = useState(() => {
    const saved = sessionStore.get("ochakovo:career-direction");
    sessionStore.remove("ochakovo:career-direction");
    return saved ?? "all";
  });
  const [type, setType] = useState("all");
  const filtered = offers.filter(
    (o) =>
      (filter === "all" ||
        (filter === "mine"
          ? direction === "undecided" || o.direction === direction
          : o.direction === filter)) &&
      (type === "all" || o.type === type),
  );
  return (
    <>
      <p className="eyebrow">КАРЬЕРНЫЙ СТАРТ</p>
      <h1 className="page-title">Открой своё дело</h1>
      <p className="muted">
        Практика и первая работа. Смотри задачи, выбирай направление и знакомься
        с командой.
      </p>
      <div className="notice small">
        Предложения демонстрационные. Условия, оплата и наличие мест требуют
        подтверждения компании.
      </div>
      <div className="row spread">
        <button
          className="button-ghost"
          onClick={() => navigate("applications")}
        >
          Мои отклики ({applications.length}) →
        </button>
      </div>
      <div className="chips">
        <button
          className={`chip ${filter === "all" ? "selected" : ""}`}
          onClick={() => setFilter("all")}
        >
          Все направления
        </button>
        <button
          className={`chip ${filter === "mine" ? "selected" : ""}`}
          onClick={() => setFilter("mine")}
        >
          По моим интересам
        </button>
      </div>
      <label className="field">
        Направление
        <select
          className="form-select"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Все направления</option>
          <option value="mine">По моим интересам</option>
          {Object.entries(DIRECTIONS)
            .filter(([id]) => id !== "undecided")
            .map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
        </select>
      </label>
      <label className="field">
        Формат
        <select
          className="form-select"
          value={type}
          onChange={(e) => setType(e.target.value)}
        >
          <option value="all">Все форматы</option>
          {[...new Set(offers.map((o) => o.type))].map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
      </label>
      {filtered.length ? (
        filtered.map((o) => (
          <OfferCard
            key={o.id}
            offer={o}
            applied={applications.some((a) => a.offer === o.id)}
          />
        ))
      ) : (
        <Empty>
          По этим условиям предложений пока нет. Попробуй выбрать другое
          направление.
        </Empty>
      )}
      <p className="small muted">
        Баллы и прохождение игр не ограничивают доступ к отклику.
      </p>
    </>
  );
}
function OfferDetail({
  offer,
  profile,
  application,
  onApply,
}: {
  offer: Offer;
  profile: Profile;
  application?: Application;
  onApply: () => void;
}) {
  return (
    <>
      <Back page="career" />
      <div className="row spread">
        <p className="eyebrow">{offer.type}</p>
        <DemoTag />
      </div>
      <h1 className="page-title">{offer.title}</h1>
      <p>{offer.description}</p>
      <dl className="card detail-list">
        <div>
          <dt>Место</dt>
          <dd>{offer.location}</dd>
        </div>
        <div>
          <dt>График</dt>
          <dd>{offer.schedule}</dd>
        </div>
        <div>
          <dt>Оплата</dt>
          <dd>{offer.pay}</dd>
        </div>
        <div>
          <dt>Сроки</dt>
          <dd>{offer.deadline ?? "Уточняются перед запуском набора"}</dd>
        </div>
      </dl>
      <section className="stack">
        <h2>Чем предстоит заниматься</h2>
        <ul>
          {offer.tasks.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
        <h2>Что пригодится</h2>
        <ul>
          {offer.requirements.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      </section>
      <div className="notice small">
        Отклик отправляется отдельно от сохранения профиля. Твои игровые баллы
        не определяют приоритет найма.
      </div>
      {application ? (
        <>
          <p className="success">
            Отклик отправлен ·{" "}
            {STATUSES[application.status] ?? application.status}
          </p>
          <Button secondary onClick={() => navigate("applications")}>
            Мои отклики
          </Button>
        </>
      ) : (
        <Button onClick={onApply}>Откликнуться с моим профилем</Button>
      )}
      <p className="small muted">
        {profile.fullName} · {profile.contact}
      </p>
      <button className="button-ghost" onClick={() => navigate("edit-profile")}>
        Проверить и изменить профиль →
      </button>
    </>
  );
}

function Events({
  events,
  registrations,
}: {
  events: CareerEvent[];
  registrations: Bootstrap["registrations"];
}) {
  const firstDate = events[0]?.date ?? "2026-10-24";
  const [month, setMonth] = useState(new Date(firstDate + "T12:00:00+03:00"));
  const [day, setDay] = useState("");
  const monthKey = `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, "0")}`;
  const firstWeekday =
    (new Date(month.getFullYear(), month.getMonth(), 1).getDay() + 6) % 7;
  const count = new Date(
    month.getFullYear(),
    month.getMonth() + 1,
    0,
  ).getDate();
  const shown = events.filter((e) => !day || e.date === day);
  return (
    <>
      <h1 className="page-title">Встретимся в Очаково</h1>
      <p className="muted">Экскурсии, встречи и знакомство с командой.</p>
      <section className="calendar card stack">
        <div className="calendar-head row spread">
          <button
            aria-label="Предыдущий месяц"
            className="button-ghost"
            onClick={() => {
              setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 15));
              setDay("");
            }}
          >
            ←
          </button>
          <h2 className="section-title">
            {month.toLocaleDateString("ru-RU", {
              month: "long",
              year: "numeric",
            })}
          </h2>
          <button
            aria-label="Следующий месяц"
            className="button-ghost"
            onClick={() => {
              setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 15));
              setDay("");
            }}
          >
            →
          </button>
        </div>
        <div className="calendar-grid">
          {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((d) => (
            <span className="small muted" key={d}>
              {d}
            </span>
          ))}
          {Array.from({ length: firstWeekday }, (_, i) => (
            <span key={`blank${i}`} />
          ))}
          {Array.from({ length: count }, (_, i) => {
            const key = `${monthKey}-${String(i + 1).padStart(2, "0")}`;
            const has = events.some((e) => e.date === key);
            return (
              <button
                className={`calendar-day ${has ? "has-event" : ""} ${day === key ? "selected" : ""}`}
                key={key}
                aria-label={`${i + 1} ${month.toLocaleDateString("ru-RU", { month: "long" })}${has ? ", есть события" : ""}`}
                aria-pressed={day === key}
                onClick={() => setDay(day === key ? "" : key)}
              >
                {i + 1}
              </button>
            );
          })}
        </div>
        <p className="small muted">
          Даты и события — демонстрационные. Время московское.
        </p>
      </section>
      <div className="row spread">
        <button className="button-ghost" onClick={() => setDay("")}>
          Все события
        </button>
        <button
          className="button-ghost"
          onClick={() => navigate("registrations")}
        >
          Мои записи (
          {registrations.filter((r) => r.status !== "cancelled").length})
        </button>
      </div>
      {day && (
        <p className="small muted">
          События {date(day)}{" "}
          <button className="button-ghost" onClick={() => setDay("")}>
            Сбросить ×
          </button>
        </p>
      )}
      {shown.length ? (
        shown.map((e) => (
          <button
            className="card card-click stack"
            key={e.id}
            onClick={() => navigate("event", e.id)}
          >
            <div className="row spread">
              <p className="eyebrow">{e.type}</p>
              <DemoTag />
            </div>
            <h2>{e.title}</h2>
            <p className="small muted">
              {date(e.date)} · {e.startTime} МСК
            </p>
            <p className="small muted">{e.location}</p>
            <p className="small">
              Свободно {e.remaining} мест{" "}
              {registrations.some(
                (r) => r.event === e.id && r.status !== "cancelled",
              )
                ? "· Ты записан ✓"
                : ""}
            </p>
            <span className="tag tag-red">Подробнее →</span>
          </button>
        ))
      ) : (
        <Empty>
          На этот день событий нет. Выбери другую дату или открой все события.
        </Empty>
      )}
    </>
  );
}

function Points({ data, goal }: { data: Bootstrap; goal: string }) {
  const [tab, setTab] = useState("catalog");
  const reward =
    data.catalog.rewards.find((r) => r.id === goal) ?? data.catalog.rewards[0];
  return (
    <>
      <Back />
      <h1 className="page-title">Мои баллы</h1>
      <section className="points-hero stack">
        <p className="eyebrow">ТВОЙ БАЛАНС</p>
        <strong className="points-value">{data.balance} б.</strong>
        <p className="small">За любопытство и новые открытия.</p>
      </section>
      {reward && (
        <button
          className="card card-click stack"
          onClick={() => navigate("reward", reward.id)}
        >
          <div className="row spread">
            <strong>{reward.title}</strong>
            <span className="small">
              {Math.min(data.balance, reward.cost)} / {reward.cost}
            </span>
          </div>
          <div className="progress-track">
            <div
              className="progress-fill"
              style={{
                width: `${Math.min(100, (data.balance / reward.cost) * 100)}%`,
              }}
            />
          </div>
          <p className="small muted">
            {data.balance >= reward.cost
              ? "Баллов хватает на цель"
              : `Ещё ${reward.cost - data.balance} баллов до цели`}
          </p>
        </button>
      )}
      <div className="chips">
        {[
          ["catalog", "Награды"],
          ["history", "История"],
          ["rules", "Правила"],
        ].map(([key, title]) => (
          <button
            className={`chip ${tab === key ? "selected" : ""}`}
            key={key}
            onClick={() => setTab(key)}
          >
            {title}
          </button>
        ))}
      </div>
      {tab === "catalog" ? (
        <>
          <p className="small muted">
            Каталог демонстрационный. Наличие и выдачу подтвердит компания.
          </p>
          {data.catalog.rewards.map((r) => (
            <button
              className="card card-click reward-card row"
              key={r.id}
              onClick={() => navigate("reward", r.id)}
            >
              <span className="card-icon" aria-hidden="true">
                ◇
              </span>
              <div className="card-copy stack">
                <h2>{r.title}</h2>
                <p className="small muted">
                  {r.cost} б. ·{" "}
                  {data.exchanges.some((e) => e.reward === r.id)
                    ? "Обмен сохранён ✓"
                    : `Доступно: ${r.remaining}`}
                </p>
              </div>
              <span>→</span>
            </button>
          ))}
        </>
      ) : tab === "history" ? (
        <>
          {data.ledger.length ? (
            data.ledger.map((l) => (
              <article className="ledger-item row spread" key={l.id}>
                <div className="stack">
                  <strong>{ledgerTitle(l.reason, data)}</strong>
                  <span className="small muted">{date(l.created)}</span>
                </div>
                <strong className={l.delta > 0 ? "text-red" : ""}>
                  {l.delta > 0 ? "+" : ""}
                  {l.delta} б.
                </strong>
              </article>
            ))
          ) : (
            <Empty>История появится после первого завершённого задания.</Empty>
          )}
        </>
      ) : (
        <div className="card stack">
          <h2>За что начисляются баллы</h2>
          <p>
            За содержательное завершение нового уровня. Награда указана на
            карточке задания.
          </p>
          <p>
            Повторное прохождение сохраняет результат, но не начисляет призовые
            баллы снова. Подсказки доступны без штрафа.
          </p>
          <p>
            За профиль, отклик и запись на событие баллы не начисляются. Они не
            влияют на приоритет найма.
          </p>
          <p>
            В демонстрации каждая награда доступна для обмена один раз. Реальная
            выдача не обещается.
          </p>
        </div>
      )}
    </>
  );
}
function ledgerTitle(reason: string, data: Bootstrap) {
  const task = data.catalog.tasks.find((t) => reason.includes(t.id));
  const reward = data.catalog.rewards.find((r) => reason.includes(r.id));
  return task
    ? `${task.title} · уровень ${task.level}`
    : reward
      ? `Обмен: ${reward.title}`
      : reason;
}

function Modal({
  title,
  onClose,
  children,
  busy,
}: React.PropsWithChildren<{
  title: string;
  onClose: () => void;
  busy: boolean;
}>) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const element = ref.current;
    element?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
      if (event.key === "Tab" && element) {
        const items = [
          ...element.querySelectorAll<HTMLElement>(
            'button:not([disabled]),a[href],input,select,[tabindex="0"]',
          ),
        ];
        const first = items[0],
          last = items[items.length - 1];
        if (!first) {
          event.preventDefault();
          return;
        }
        if (
          event.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === element)
        ) {
          event.preventDefault();
          last.focus();
        } else if (
          !event.shiftKey &&
          (document.activeElement === last ||
            document.activeElement === element)
        ) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [busy, onClose]);
  return (
    <div
      className="modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div
        className="modal stack"
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        <div className="row spread">
          <h2 id="modal-title">{title}</h2>
          <button
            className="button-ghost"
            disabled={busy}
            onClick={onClose}
            aria-label="Закрыть"
          >
            ×
          </button>
        </div>
        {children}
        <button className="button-ghost" disabled={busy} onClick={onClose}>
          Вернуться
        </button>
      </div>
    </div>
  );
}
function Privacy() {
  return (
    <>
      <h1 className="page-title">Данные и согласия</h1>
      <p>
        Этот проект — демонстрационный прототип «Очаково: изнутри». Используй
        вымышленные данные. Перед запуском для реальных кандидатов компания
        должна утвердить оператора, сроки хранения, основания обработки и
        политику.
      </p>
      <section className="card stack">
        <h2>Что сохраняет прототип</h2>
        <p>
          Профиль, игровой прогресс, историю баллов, отклики, записи и обмены.
          Отклик хранит копию профиля на момент отправки.
        </p>
        <p>
          Профиль используется для подбора направлений, заполнения заявки и
          записи. Он сам по себе не является откликом.
        </p>
        <p>
          Согласие на будущие предложения — отдельный необязательный выбор. Его
          можно изменить в профиле.
        </p>
        <p>
          Данные хранятся в базе этого приложения. Кабинет HR защищён отдельным
          ключом. Автоматической отправки в кадровую систему или переписки от
          имени компании нет.
        </p>
      </section>
      <p className="small muted">
        Запуск с реальными персональными данными требует утверждённой политики и
        процедур удаления/отзыва согласия.
      </p>
    </>
  );
}

function Admin() {
  const [adminToken, setAdminToken] = useState("");
  const [items, setItems] = useState<Application[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function adminRequest(path: string, method = "GET", body?: unknown) {
    const response = await fetch("/api/admin" + path, {
      method,
      headers: {
        Authorization: `Bearer ${adminToken}`,
        "Content-Type": "application/json",
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const result = await response.json();
    if (!response.ok)
      throw new Error(result.error?.message ?? result.error ?? "Нет доступа");
    return result;
  }
  async function load(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await adminRequest("/applications");
      setItems(Array.isArray(r) ? r : r.applications);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка запроса");
    } finally {
      setBusy(false);
    }
  }
  async function update(id: string, status: string) {
    setBusy(true);
    setError("");
    try {
      await adminRequest(`/applications/${id}`, "PATCH", { status });
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="app-shell screen stack">
      <p className="eyebrow">КАБИНЕТ HR · ДЕМОНСТРАЦИЯ</p>
      <h1 className="page-title">Принятые отклики</h1>
      {items === null ? (
        <form className="stack" onSubmit={load}>
          <label className="field">
            Ключ администратора
            <input
              className="form-input"
              autoComplete="off"
              type="password"
              value={adminToken}
              onChange={(e) => setAdminToken(e.target.value)}
              required
            />
          </label>
          <Button disabled={busy}>Открыть заявки</Button>
          <p className="small muted">
            Ключ хранится на сервере в .data/admin-token; он не встраивается в
            клиент.
          </p>
        </form>
      ) : (
        <>
          <div className="row spread">
            <p>{items.length} заявок</p>
            <button
              className="button-ghost"
              onClick={() => void load()}
              disabled={busy}
            >
              Обновить
            </button>
            <button
              className="button-ghost"
              onClick={() => {
                setItems(null);
                setAdminToken("");
              }}
            >
              Выйти
            </button>
          </div>
          {items.length ? (
            items.map((a) => (
              <article className="card stack" key={a.id}>
                <p className="eyebrow">
                  {a.offer} · № {a.id.slice(0, 8)}
                </p>
                <ProfileSummary profile={a.profile} />
                <p className="small muted">Получен {date(a.created)}</p>
                <label className="field">
                  Статус
                  <select
                    className="form-select"
                    disabled={busy}
                    value={a.status}
                    onChange={(e) => void update(a.id, e.target.value)}
                  >
                    {[
                      "sent",
                      "reviewing",
                      "contacted",
                      "accepted",
                      "rejected",
                    ].map((s) => (
                      <option key={s} value={s}>
                        {STATUSES[s]}
                      </option>
                    ))}
                  </select>
                </label>
              </article>
            ))
          ) : (
            <Empty>Заявок пока нет.</Empty>
          )}
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <a href="#/home" className="button-ghost">
        В приложение →
      </a>
    </main>
  );
}
