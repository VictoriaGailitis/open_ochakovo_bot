import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { api, ApiError, setDemoIdentity } from "../api";
import { sessionStore } from "../storage";
import { Mascot } from "../components/Art";
import type {
  Goal,
  HelpRequest,
  Meeting,
  Placement,
  PracticeData,
} from "./types";
import {
  calendarDays,
  date,
  goalLabels,
  localInput,
  meetingLabels,
  moscowDate,
  practiceLabels,
  progress,
  report,
  requestLabels,
  shiftMonth,
  time,
} from "./utils";
import "./practice.css";

type Action = (
  path: string,
  method: string,
  body: unknown,
  message?: string,
  next?: string,
) => Promise<boolean>;
type Go = (screen: string, item?: string) => void;
const closed = (p: Placement) => ["completed", "cancelled"].includes(p.status);
const parse = () =>
  location.hash
    .replace(/^#\/?/, "")
    .split("/")
    .map((part) => {
      try {
        return decodeURIComponent(part);
      } catch {
        return part;
      }
    });
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
function Card({
  title,
  sub,
  icon = "→",
  onClick,
}: {
  title: string;
  sub: string;
  icon?: string;
  onClick: () => void;
}) {
  return (
    <button className="p-card-link" onClick={onClick}>
      <span className="p-icon" aria-hidden="true">
        {icon}
      </span>
      <span>
        <strong>{title}</strong>
        <small>{sub}</small>
      </span>
      <span aria-hidden="true">›</span>
    </button>
  );
}
function Empty({ children }: { children: ReactNode }) {
  return (
    <div className="card p-empty">
      <p>{children}</p>
    </div>
  );
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="p-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function Back({ go, screen = "home" }: { go: Go; screen?: string }) {
  return (
    <button className="button-ghost back-link" onClick={() => go(screen)}>
      ← Назад
    </button>
  );
}
function Status({ children }: { children: ReactNode }) {
  return <span className="tag p-status">{children}</span>;
}
function Contact({ value }: { value: string }) {
  const email = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  const phone = /^\+?[\d ()-]{10,25}$/.test(value);
  return email || phone ? (
    <a
      className="p-contact"
      href={email ? `mailto:${value}` : `tel:${value.replace(/[^+\d]/g, "")}`}
    >
      {value}
    </a>
  ) : (
    <p>{value}</p>
  );
}

export function PracticeApp({ mode }: { mode: string }) {
  const [route, setRoute] = useState(parse);
  const [data, setData] = useState<PracticeData | null>(null);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [toast, setToast] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false),
    generation = useRef(0),
    heading = useRef<HTMLElement>(null);
  const mentorView = route[0] === "mentor",
    screen = route[1] || "home",
    pid = route[2],
    item = route[3];
  const reload = useCallback(async () => {
    const n = ++generation.current;
    const result = await api<PracticeData>("/practice/bootstrap");
    if (n === generation.current) setData(result);
    return result;
  }, []);
  useEffect(() => {
    let alive = true;
    void reload()
      .catch((e) => {
        if (alive) setError(e.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
      generation.current++;
    };
  }, [reload]);
  useEffect(() => {
    const changed = () => {
      setRoute(parse());
      setError("");
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", changed);
    return () => window.removeEventListener("hashchange", changed);
  }, []);
  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
  }, [route.join("/")]);
  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 5000);
    return () => clearTimeout(t);
  }, [toast]);
  const list = mentorView ? (data?.mentees ?? []) : (data?.practices ?? []);
  const p =
    list.find((x) => x.id === pid) ??
    (!pid ? (list.find((x) => x.status === "active") ?? list[0]) : undefined);
  const go: Go = (s, i) => {
    location.hash = `/${mentorView ? "mentor" : "practice"}/${s}${p ? "/" + encodeURIComponent(p.id) : ""}${i ? "/" + encodeURIComponent(i) : ""}`;
  };
  const run: Action = async (
    path,
    method,
    body,
    message = "Сохранено",
    next,
  ) => {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await api(path, method, body);
      await reload();
      setToast(message);
      if (next) go(next);
      return true;
    } catch (e) {
      setError(
        e instanceof Error
          ? e.message
          : "Не удалось сохранить. Повтори попытку.",
      );
      if (e instanceof ApiError && e.status === 409)
        await reload().catch(() => {});
      return false;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  async function seedDemo() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const ids = await api<{
        mentorDevUserId: string;
        internDevUserId: string;
      }>("/practice/demo", "POST", {});
      sessionStore.set("ochakovo:practice:demo-mentor", ids.mentorDevUserId);
      sessionStore.set("ochakovo:practice:demo-intern", ids.internDevUserId);
      await reload();
      setToast("Демонстрационная практика готова");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось создать демо.");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  const demoOther = sessionStore.get(
    `ochakovo:practice:demo-${mentorView ? "intern" : "mentor"}`,
  );
  const nav = mentorView
    ? [
        ["home", "⌂", "Практиканты"],
        ["calendar", "▦", "Встречи"],
        ["goals", "◎", "Цели"],
        ["feedback", "♡", "Отзывы"],
      ]
    : [
        ["home", "⌂", "Практика"],
        ["calendar", "▦", "Календарь"],
        ["goals", "◎", "Цели"],
        ["team", "♧", "Команда"],
      ];
  const active = ["goal"].includes(screen)
    ? "goals"
    : ["meeting"].includes(screen)
      ? "calendar"
      : screen;
  let content: ReactNode;
  if (loading) content = <p role="status">Загружаем практику…</p>;
  else if (!data)
    content = (
      <>
        <h1>Не удалось загрузить практику</h1>
        <Button
          disabled={busy}
          onClick={() => {
            setLoading(true);
            setError("");
            void reload()
              .catch((e) => setError(e.message))
              .finally(() => setLoading(false));
          }}
        >
          Повторить
        </Button>
      </>
    );
  else if (mentorView && !data.mentor)
    content = (
      <>
        <h1>Кабинет наставника</h1>
        <Empty>
          Аккаунт пока не связан с наставником. Доступ назначает администратор.
        </Empty>
      </>
    );
  else if (mentorView && screen === "home")
    content = (
      <MentorHome
        data={data}
        select={(id) => {
          location.hash = `/mentor/student/${id}`;
        }}
      />
    );
  else if (!p)
    content = (
      <>
        <h1>{pid ? "Практика недоступна" : "Моя практика"}</h1>
        <Empty>
          {pid
            ? "Эта практика не найдена или не назначена тебе."
            : "Когда администратор подтвердит выход и создаст практику, здесь появятся даты, наставник и твой план."}
        </Empty>
        {data.demo && !mentorView && (
          <div className="card stack">
            <h2>Попробовать на примере</h2>
            <p className="small muted">
              Отдельные учебные данные: практика, наставник, цели и встреча.
              Существующий профиль сохраняется.
            </p>
            <Button disabled={busy} onClick={() => void seedDemo()}>
              Создать демопрактику
            </Button>
          </div>
        )}
      </>
    );
  else {
    const common = { p, go, run, busy, mentorView };
    switch (screen) {
      case "home":
      case "student":
        content = <Home {...common} today={data.today} week={data.week} />;
        break;
      case "start":
        content = <FirstDays {...common} />;
        break;
      case "mentor":
        content = <MentorCard {...common} />;
        break;
      case "team":
        content = <Team {...common} />;
        break;
      case "goals":
        content = <Goals {...common} />;
        break;
      case "goal":
        content = (
          <GoalDetail {...common} goal={p.goals.find((g) => g.id === item)} />
        );
        break;
      case "calendar":
        content = <Calendar {...common} today={data.today} />;
        break;
      case "meeting":
        content = (
          <MeetingDetail
            {...common}
            meeting={p.meetings.find((m) => m.id === item)}
          />
        );
        break;
      case "mood":
        content = (
          <CheckinForm
            key={`${p.id}:${data.week}`}
            {...common}
            week={data.week}
          />
        );
        break;
      case "help":
      case "requests":
        content = <Requests {...common} />;
        break;
      case "career":
        content = <Career {...common} />;
        break;
      case "results":
      case "feedback":
        content = <Results {...common} />;
        break;
      case "finish":
        content = <Finish {...common} />;
        break;
      default:
        content = (
          <>
            <h1>Экран не найден</h1>
            <Button onClick={() => go("home")}>К практике</Button>
          </>
        );
    }
  }
  return (
    <div className={`app-shell p-shell ${mentorView ? "p-mentor-shell" : ""}`}>
      <header className="app-header">
        <a href="#/home" className="brand">
          Очаково: изнутри
        </a>
        <span className="tag">{mentorView ? "Наставник" : "Практикант"}</span>
      </header>
      <main ref={heading} tabIndex={-1} className="screen p-content stack">
        <a className="p-return" href="#/home">
          ← Карьерный раздел
        </a>
        {mode === "demo" && (
          <div className="p-demo">
            <span>Локальная демонстрация</span>
            {demoOther && (
              <button
                disabled={busy}
                onClick={() => {
                  setDemoIdentity(demoOther);
                  location.hash = mentorView ? "/practice" : "/mentor";
                  location.reload();
                }}
              >
                Открыть как {mentorView ? "практикант" : "наставник"}
              </button>
            )}
          </div>
        )}
        {error && (
          <div className="error" role="alert">
            {error}
          </div>
        )}
        {p && mentorView && screen !== "home" && (
          <p className="small muted">{p.studentName} · {p.title}</p>
        )}
        {p && list.length > 1 && (
          <Field label={mentorView ? "Практикант" : "Период практики"}>
            <select
              value={p.id}
              onChange={(e) => {
                location.hash = `/${mentorView ? "mentor" : "practice"}/${mentorView ? "student" : "home"}/${e.target.value}`;
              }}
            >
              {list.map((x) => (
                <option key={x.id} value={x.id}>
                  {mentorView ? x.studentName : x.title} · {date(x.start_date)}
                </option>
              ))}
            </select>
          </Field>
        )}
        {p && closed(p) && (
          <div className="p-note" role="status">
            Практика {p.status === "completed" ? "завершена" : "отменена"}.
            Результаты доступны для просмотра.
          </div>
        )}
        <section
          key={`${mentorView}:${p?.id ?? "empty"}:${screen}:${item ?? ""}`}
          className="stack"
        >
          {content}
        </section>
      </main>
      <nav
        className="bottom-nav"
        aria-label={mentorView ? "Навигация наставника" : "Моя практика"}
      >
        {nav.map(([key, icon, label]) => (
          <button
            key={key}
            className={`nav-item ${active === key || (key === "home" && !["calendar", "goals", "team", "feedback"].includes(active)) ? "active" : ""}`}
            aria-current={active === key ? "page" : undefined}
            onClick={() => go(key)}
          >
            <span aria-hidden="true">{icon}</span>
            <span>{label}</span>
          </button>
        ))}
      </nav>
      {toast && (
        <div className="toast" role="status">
          {toast}
        </div>
      )}
    </div>
  );
}

type Props = {
  p: Placement;
  go: Go;
  run: Action;
  busy: boolean;
  mentorView: boolean;
};
function Home({
  p,
  go,
  today,
  week,
  mentorView,
}: Props & { today: string; week: string }) {
  const completed = p.goals.filter((g) => g.status === "approved").length;
  const upcoming = p.meetings
    .filter((m) => m.status === "scheduled" && new Date(m.ends_at) > new Date())
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0];
  return (
    <>
      <div className="stack">
        <h1>{mentorView ? p.studentName : "Моя практика"}</h1>
        <p className="muted">
          {mentorView
            ? p.title
            : `${p.studentName.split(" ")[0]}, ты уже часть команды.`}
        </p>
      </div>
      <div className="hero stack p-hero">
        <Status>{practiceLabels[p.status]}</Status>
        <div className="row">
          <div className="stack">
            <h2>ТВОЙ ВКУС К ДЕЛУ</h2>
            <p className="small">{p.title}</p>
            <p className="small">
              {date(p.start_date)} — {date(p.end_date)}
            </p>
          </div>
          <Mascot />
        </div>
        <progress
          max={100}
          value={progress(p, today)}
          aria-label="Период практики"
        />
      </div>
      <h2>Ближайший шаг</h2>
      {upcoming ? (
        <Card
          title={upcoming.title}
          sub={`${date(upcoming.starts_at)} · ${time(upcoming.starts_at)}–${time(upcoming.ends_at)}`}
          icon="▦"
          onClick={() => go("meeting", upcoming.id)}
        />
      ) : (
        <Empty>Ближайшая встреча пока не назначена.</Empty>
      )}
      {!mentorView && !closed(p) && (
        <Card
          title={
            p.checkins?.some((c) => c.week === week)
              ? "Твоя обратная связь за неделю"
              : "Как проходит твоя неделя?"
          }
          sub="Добровольный опрос · Можно пропускать вопросы"
          icon="♡"
          onClick={() => go("mood")}
        />
      )}
      <div className="p-grid">
        <Card
          title="Цели и навыки"
          sub={`${completed} из ${p.goals.length} подтверждены`}
          icon="◎"
          onClick={() => go("goals")}
        />
        <Card
          title={mentorView ? "Результаты" : "Твой наставник"}
          sub={
            mentorView
              ? "Обратная связь и освоенные навыки"
              : (p.mentor?.name ?? "Пока не назначен")
          }
          icon="♧"
          onClick={() => go(mentorView ? "feedback" : "mentor")}
        />
      </div>
      <div className="p-link-row">
        <button className="button-ghost" onClick={() => go("help")}>
          {mentorView ? "Обращения практиканта" : "Нужна помощь"} →
        </button>
        {!mentorView && (
          <button className="button-ghost" onClick={() => go("career")}>
            Хочу остаться →
          </button>
        )}
      </div>
      <Card
        title="Первые дни"
        sub="Знакомство, документы и правила"
        onClick={() => go("start")}
      />
      <Card
        title="Завершение практики"
        sub="Результаты, документы и следующий шаг"
        onClick={() => go("finish")}
      />
    </>
  );
}
function MentorCard({ p, go }: Props) {
  const m = p.mentor;
  return (
    <>
      <Back go={go} />
      <h1>Рядом есть наставник</h1>
      {m ? (
        <>
          <div className="card stack">
            <span className="p-avatar">
              {m.name
                .split(" ")
                .slice(0, 2)
                .map((n) => n[0])
                .join("")}
            </span>
            <h2>{m.name}</h2>
            <p className="muted">{m.position}</p>
            <p>{m.about}</p>
          </div>
          <div className="card stack">
            <h2>Когда можно обратиться</h2>
            <p>{m.office_hours || "Уточни удобное время у наставника."}</p>
            <Contact value={m.contact} />
          </div>
          <Button onClick={() => go("help")}>Обсудить вопрос</Button>
        </>
      ) : (
        <Empty>
          Наставник ещё не назначен. Можно связаться с координатором практики.
        </Empty>
      )}
      <Button secondary onClick={() => go("team")}>
        Контакты команды
      </Button>
    </>
  );
}
function Team({ p, go }: Props) {
  return (
    <>
      <Back go={go} />
      <h1>Моя команда</h1>
      <p className="muted">Ты знаешь, к кому обратиться.</p>
      {p.mentor ? (
        <Card
          title={p.mentor.name}
          sub={`${p.mentor.position} · Наставник`}
          icon="♧"
          onClick={() => go("mentor")}
        />
      ) : (
        <Empty>Наставник ещё не назначен.</Empty>
      )}
      {p.coordinator?.name && (
        <div className="card stack">
          <h2>{p.coordinator.name}</h2>
          <p className="small muted">
            Координатор · График, документы и продолжение работы
          </p>
          <Contact value={p.coordinator.contact} />
        </div>
      )}
      <Button secondary onClick={() => go("help")}>
        Мне нужна помощь
      </Button>
    </>
  );
}
const steps = [
  ["arrival", "Уточнить место и время встречи"],
  ["documents", "Подготовить документы"],
  ["safety", "Пройти инструктаж с наставником"],
  ["team", "Познакомиться с командой"],
];
function FirstDays({ p, go, run, busy, mentorView }: Props) {
  return (
    <>
      <Back go={go} />
      <h1>Первые дни</h1>
      <div className="p-note stack">
        <h2>Начинаем вместе</h2>
        <p>
          {p.arrival ||
            "Подробности первого дня уточни у наставника или координатора."}
        </p>
      </div>
      <h2>Твои первые шаги</h2>
      {steps.map(([id, label]) => (
        <label className="p-check card" key={id}>
          <input
            type="checkbox"
            checked={p.onboarding.includes(id)}
            disabled={busy || mentorView || closed(p)}
            onChange={(e) =>
              void run(
                `/practice/${p.id}/onboarding`,
                "PUT",
                {
                  steps: e.target.checked
                    ? [...p.onboarding, id]
                    : p.onboarding.filter((x) => x !== id),
                },
                "План обновлён",
              )
            }
          />
          <span>{label}</span>
        </label>
      ))}
      <Button secondary onClick={() => go("mentor")}>
        Открыть контакты наставника
      </Button>
    </>
  );
}
function Goals(props: Props) {
  const { p, go, mentorView } = props;
  const approved = p.goals.filter((g) => g.status === "approved").length;
  return (
    <>
      <Back go={go} screen={mentorView ? "student" : "home"} />
      <h1>Цели практики</h1>
      <div className="p-note stack">
        <h2>Мой маршрут в профессии</h2>
        <p>
          {approved} из {p.goals.length} целей подтверждены
        </p>
        {p.goals.length > 0 && (
          <progress
            max={p.goals.length}
            value={approved}
            aria-label="Подтверждённые цели"
          />
        )}
      </div>
      {p.goals.length ? (
        p.goals.map((g) => (
          <Card
            key={g.id}
            title={g.title}
            sub={`${goalLabels[g.status]} · До ${date(g.due_date)}`}
            icon={g.status === "approved" ? "✓" : "◎"}
            onClick={() => go("goal", g.id)}
          />
        ))
      ) : (
        <Empty>Цели пока не согласованы. Обсудите их с наставником.</Empty>
      )}
      {mentorView && !closed(p) && <GoalForm {...props} />}
      <button className="button-ghost" onClick={() => go("results")}>
        Мои результаты →
      </button>
    </>
  );
}
function GoalDetail(props: Props & { goal?: Goal }) {
  const { p, goal, go, run, busy, mentorView } = props;
  const [comment, setComment] = useState(goal?.mentor_comment ?? "");
  if (!goal)
    return (
      <>
        <Back go={go} screen="goals" />
        <Empty>Цель не найдена.</Empty>
      </>
    );
  const next =
    goal.status === "planned"
      ? "in_progress"
      : goal.status === "in_progress"
        ? "review"
        : mentorView && goal.status === "review"
          ? "approved"
          : null;
  return (
    <>
      <Back go={go} screen="goals" />
      <Status>{goalLabels[goal.status]}</Status>
      <h1>{goal.title}</h1>
      <p className="small muted">До {date(goal.due_date)}</p>
      <p>{goal.description}</p>
      <div className="card stack">
        <h2>Как поймём, что получилось</h2>
        <p className="p-prewrap">{goal.criteria}</p>
      </div>
      {goal.mentor_comment && (
        <div className="p-note stack">
          <h2>Комментарий наставника</h2>
          <p className="p-prewrap">{goal.mentor_comment}</p>
        </div>
      )}
      {!closed(p) && (
        <>
          {mentorView && goal.status !== "approved" && (
            <GoalForm {...props} editGoal={goal} />
          )}{" "}
          {mentorView && (
            <Field label="Комментарий к результату">
              <textarea
                maxLength={2000}
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </Field>
          )}
          {next && (
            <Button
              disabled={busy}
              onClick={() =>
                void run(
                  `/practice/${p.id}/goals/${goal.id}`,
                  "PATCH",
                  {
                    status: next,
                    version: goal.version,
                    mentorComment: comment,
                  },
                  next === "approved"
                    ? "Результат подтверждён"
                    : "Статус цели обновлён",
                  "goals",
                )
              }
            >
              {next === "in_progress"
                ? "Начать работу"
                : next === "review"
                  ? "Отправить на проверку"
                  : "Подтвердить результат"}
            </Button>
          )}
          {mentorView && goal.status === "review" && (
            <Button
              secondary
              disabled={busy}
              onClick={() =>
                void run(
                  `/practice/${p.id}/goals/${goal.id}`,
                  "PATCH",
                  {
                    status: "in_progress",
                    version: goal.version,
                    mentorComment: comment,
                  },
                  "Цель возвращена в работу",
                  "goals",
                )
              }
            >
              Вернуть на доработку
            </Button>
          )}
          {!mentorView && goal.status === "review" && (
            <p className="small muted">
              Наставник проверит результат и оставит обратную связь.
            </p>
          )}
        </>
      )}
    </>
  );
}
function GoalForm({ p, run, busy, editGoal }: Props & { editGoal?: Goal }) {
  const [title, setTitle] = useState(editGoal?.title ?? ""),
    [description, setDescription] = useState(editGoal?.description ?? ""),
    [criteria, setCriteria] = useState(editGoal?.criteria ?? ""),
    [due, setDue] = useState(editGoal?.due_date ?? p.end_date);
  const key = useRef(crypto.randomUUID());
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      await run(
        `/practice/${p.id}/goals${editGoal ? "/" + editGoal.id : ""}`,
        editGoal ? "PATCH" : "POST",
        {
          title,
          description,
          criteria,
          dueDate: due,
          version: editGoal?.version,
          clientKey: key.current,
        },
        editGoal ? "Цель обновлена" : "Цель добавлена",
      )
    ) {
      if (!editGoal) {
        setTitle("");
        setDescription("");
        setCriteria("");
      }
      key.current = crypto.randomUUID();
    }
  }
  return (
    <details className="p-details">
      <summary>{editGoal ? "Изменить цель" : "Добавить цель"}</summary>
      <form className="card stack" onSubmit={submit}>
        <Field label="Название">
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Описание">
          <textarea
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </Field>
        <Field label="Критерии результата">
          <textarea
            required
            maxLength={2000}
            value={criteria}
            onChange={(e) => setCriteria(e.target.value)}
          />
        </Field>
        <Field label="Срок">
          <input
            type="date"
            required
            min={p.start_date}
            max={p.end_date}
            value={due}
            onChange={(e) => setDue(e.target.value)}
          />
        </Field>
        <Button disabled={busy} type="submit">
          {editGoal ? "Сохранить изменения" : "Добавить цель"}
        </Button>
      </form>
    </details>
  );
}
function Calendar(props: Props & { today: string }) {
  const { p, go, today, mentorView } = props;
  const [selected, setSelected] = useState(today),
    [month, setMonth] = useState(today.slice(0, 7));
  const meetings = p.meetings.filter(
      (m) => moscowDate(m.starts_at) === selected,
    ),
    goals = p.goals.filter((g) => g.due_date === selected);
  return (
    <>
      <Back go={go} screen={mentorView ? "student" : "home"} />
      <h1>Мой календарь</h1>
      <p className="small muted">Все встречи — по московскому времени.</p>
      <div className="card p-calendar">
        <div className="p-link-row">
          <button
            className="button-ghost"
            aria-label="Предыдущий месяц"
            onClick={() => {
              const m = shiftMonth(month, -1);
              setMonth(m);
              setSelected(m + "-01");
            }}
          >
            ‹
          </button>
          <h2>
            {new Date(month + "-01T12:00:00Z").toLocaleDateString("ru-RU", {
              month: "long",
              year: "numeric",
              timeZone: "Europe/Moscow",
            })}
          </h2>
          <button
            className="button-ghost"
            aria-label="Следующий месяц"
            onClick={() => {
              const m = shiftMonth(month, 1);
              setMonth(m);
              setSelected(m + "-01");
            }}
          >
            ›
          </button>
        </div>
        <div className="p-calendar-grid">
          {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((d) => (
            <span className="p-weekday" key={d}>
              {d}
            </span>
          ))}
          {calendarDays(month).map((d, i) =>
            d ? (
              <button
                key={d}
                aria-pressed={d === selected}
                aria-label={`${date(d)}${p.meetings.some((m) => moscowDate(m.starts_at) === d && m.status === "scheduled") ? ", есть встреча" : ""}`}
                className={d === selected ? "selected" : ""}
                onClick={() => setSelected(d)}
              >
                {Number(d.slice(-2))}
                <span aria-hidden="true" className="p-calendar-dot">
                  {p.meetings.some(
                    (m) =>
                      moscowDate(m.starts_at) === d && m.status === "scheduled",
                  ) || p.goals.some((g) => g.due_date === d)
                    ? "•"
                    : ""}
                </span>
              </button>
            ) : (
              <span key={i} />
            ),
          )}
        </div>
      </div>
      <h2 aria-live="polite">{date(selected)}</h2>
      {meetings.map((m) => (
        <Card
          key={m.id}
          title={m.title}
          sub={`${time(m.starts_at)}–${time(m.ends_at)} · ${meetingLabels[m.status]}`}
          icon="▦"
          onClick={() => go("meeting", m.id)}
        />
      ))}
      {goals.map((g) => (
        <Card
          key={g.id}
          title={g.title}
          sub={`Срок цели · ${goalLabels[g.status]}`}
          icon="◎"
          onClick={() => go("goal", g.id)}
        />
      ))}
      {!meetings.length && !goals.length && (
        <Empty>На этот день встреч и сроков пока нет.</Empty>
      )}
      {mentorView && !closed(p) && (
        <MeetingForm key={selected} {...props} initialDate={selected} />
      )}
      <h2>Все встречи</h2>
      {!p.meetings.length && <Empty>Встречи пока не назначены.</Empty>}
      {p.meetings.map((m) => (
        <Card
          key={m.id}
          title={m.title}
          sub={`${date(m.starts_at)} · ${time(m.starts_at)} · ${meetingLabels[m.status]}`}
          icon="▦"
          onClick={() => go("meeting", m.id)}
        />
      ))}
    </>
  );
}
function MeetingDetail(props: Props & { meeting?: Meeting }) {
  const { p, meeting: m, go, run, busy, mentorView } = props;
  if (!m)
    return (
      <>
        <Back go={go} screen="calendar" />
        <Empty>Встреча не найдена.</Empty>
      </>
    );
  return (
    <>
      <Back go={go} screen="calendar" />
      <Status>{meetingLabels[m.status]}</Status>
      <h1>{m.title}</h1>
      <div className="card stack">
        <p>
          {date(m.starts_at)} · {time(m.starts_at)}–{time(m.ends_at)}
        </p>
        <p className="muted">{m.location}</p>
        <p className="small">
          {mentorView
            ? p.studentName
            : (p.mentor?.name ?? "Наставник пока не назначен")}
        </p>
      </div>
      <h2>Что обсудим</h2>
      <p className="p-prewrap">
        {m.agenda || "Темы можно согласовать перед встречей."}
      </p>
      {!closed(p) &&
        (mentorView ? (
          <>
            <MeetingForm {...props} meeting={m} />
            {m.status === "scheduled" && (
              <>
                <Button
                  disabled={busy}
                  onClick={() =>
                    void run(
                      `/practice/${p.id}/meetings/${m.id}`,
                      "PATCH",
                      { status: "completed", version: m.version },
                      "Встреча отмечена состоявшейся",
                      "calendar",
                    )
                  }
                >
                  Встреча состоялась
                </Button>
                <Button
                  secondary
                  disabled={busy}
                  onClick={() =>
                    void run(
                      `/practice/${p.id}/meetings/${m.id}`,
                      "PATCH",
                      { status: "cancelled", version: m.version },
                      "Встреча отменена",
                      "calendar",
                    )
                  }
                >
                  Отменить встречу
                </Button>
              </>
            )}
          </>
        ) : (
          <Button secondary onClick={() => go("help")}>
            Добавить тему или попросить перенос
          </Button>
        ))}
    </>
  );
}
function MeetingForm({ p, meeting, run, busy, initialDate }: Props & {
  meeting?: Meeting;
  initialDate?: string;
}) {
  const initialDay =
    initialDate && initialDate >= p.start_date && initialDate <= p.end_date
      ? initialDate
      : p.start_date;
  const [title, setTitle] = useState(meeting?.title ?? ""),
    [location, setLocation] = useState(meeting?.location ?? ""),
    [agenda, setAgenda] = useState(meeting?.agenda ?? "");
  const [start, setStart] = useState(
      meeting ? localInput(meeting.starts_at) : initialDay + "T14:00",
    ),
    [end, setEnd] = useState(
      meeting ? localInput(meeting.ends_at) : initialDay + "T14:30",
    );
  const key = useRef(crypto.randomUUID());
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      await run(
        `/practice/${p.id}/meetings${meeting ? "/" + meeting.id : ""}`,
        meeting ? "PATCH" : "POST",
        {
          title,
          location,
          agenda,
          startsAt: start + ":00+03:00",
          endsAt: end + ":00+03:00",
          version: meeting?.version,
          clientKey: key.current,
        },
        meeting ? "Встреча перенесена" : "Встреча назначена",
      )
    ) {
      key.current = crypto.randomUUID();
      if (!meeting) {
        setTitle("");
        setAgenda("");
        setLocation("");
      }
    }
  }
  return (
    <details className="p-details">
      <summary>
        {meeting ? "Перенести или изменить встречу" : "Назначить встречу"}
      </summary>
      <form className="card stack" onSubmit={submit}>
        <Field label="Название">
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </Field>
        <Field label="Начало · Москва">
          <input
            required
            type="datetime-local"
            min={p.start_date + "T00:00"}
            max={p.end_date + "T23:59"}
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </Field>
        <Field label="Конец · Москва">
          <input
            required
            type="datetime-local"
            min={start}
            max={p.end_date + "T23:59"}
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </Field>
        <Field label="Место или ссылка">
          <input
            required
            maxLength={300}
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </Field>
        <Field label="Темы встречи">
          <textarea
            maxLength={2000}
            value={agenda}
            onChange={(e) => setAgenda(e.target.value)}
          />
        </Field>
        <Button disabled={busy} type="submit">
          Сохранить встречу
        </Button>
      </form>
    </details>
  );
}
function CheckinForm({
  p,
  go,
  run,
  busy,
  mentorView,
  week,
}: Props & { week: string }) {
  const last = p.checkins?.find((c) => c.week === week);
  const [answers, setAnswers] = useState<
    Record<string, number | string | null>
  >(last?.answers ?? {});
  const [step, setStep] = useState(1),
    [saved, setSaved] = useState(false);
  if (mentorView)
    return <Empty>Личные ответы опроса доступны только практиканту.</Empty>;
  if (saved)
    return (
      <>
        <div className="p-mascot">
          <Mascot pose={2} />
        </div>
        <h1>Спасибо, что поделилась</h1>
        <p>
          Ответы сохранены. Если нужна поддержка, можно отдельно обратиться к
          наставнику или координатору.
        </p>
        <Button onClick={() => go("help")}>Обсудить вопрос</Button>
        <Button secondary onClick={() => go("home")}>
          К моей практике
        </Button>
      </>
    );
  const questions =
    step === 1
      ? [
          ["mood", "Как ты себя чувствуешь?", "Тяжело", "Хорошо"],
          [
            "comfort",
            "Насколько комфортно в команде?",
            "Некомфортно",
            "Очень комфортно",
          ],
        ]
      : [
          [
            "workload",
            "Как тебе текущая нагрузка?",
            "Слишком низкая",
            "Слишком высокая",
          ],
          ["clarity", "Насколько понятны задачи?", "Непонятны", "Понятны"],
          ["support", "Хватает ли поддержки?", "Не хватает", "Достаточно"],
        ];
  return (
    <>
      <Back go={go} />
      <h1>Как проходит неделя</h1>
      <p className="small muted">
        Добровольно · Шаг {step} из 2 · Неделя с {date(week)}
      </p>
      <div className="p-note">
        Можно пропустить любой вопрос. Наставник не получает ответы этого
        опроса. Они не используются для оценки выполнения задач.
      </div>
      {questions.map(([key, title, min, max]) => (
        <fieldset className="p-rating" key={key}>
          <legend>{title}</legend>
          <div className="p-rating-row">
            {[1, 2, 3, 4, 5].map((n) => (
              <button
                type="button"
                key={n}
                aria-label={`${title} ${n} из 5`}
                aria-pressed={answers[key] === n}
                onClick={() =>
                  setAnswers((a) => ({ ...a, [key]: a[key] === n ? null : n }))
                }
              >
                {n}
              </button>
            ))}
          </div>
          <div className="p-rating-ends">
            <span>{min}</span>
            <span>{max}</span>
          </div>
        </fieldset>
      ))}
      {step === 2 && (
        <Field label="Что ещё хочется сказать? · Необязательно">
          <textarea
            value={String(answers.comment ?? "")}
            maxLength={2000}
            onChange={(e) =>
              setAnswers((a) => ({ ...a, comment: e.target.value }))
            }
          />
        </Field>
      )}
      {!closed(p) &&
        (step === 1 ? (
          <Button onClick={() => setStep(2)}>Продолжить</Button>
        ) : (
          <Button
            disabled={busy}
            onClick={() =>
              void run(
                `/practice/${p.id}/checkins`,
                "PUT",
                { answers },
                "Ответы сохранены",
              ).then((ok) => {
                if (ok) setSaved(true);
              })
            }
          >
            {last ? "Обновить ответы" : "Сохранить ответы"}
          </Button>
        ))}
      <div className="p-link-row">
        {step === 2 && (
          <button className="button-ghost" onClick={() => setStep(1)}>
            Назад
          </button>
        )}
        <button className="button-ghost" onClick={() => go("home")}>
          Пропустить опрос
        </button>
      </div>
    </>
  );
}
function Requests(props: Props) {
  const { p, go, run, busy, mentorView } = props;
  const [target, setTarget] = useState(p.mentor ? "mentor" : "coordinator"),
    [topic, setTopic] = useState("Вопрос по задаче"),
    [body, setBody] = useState("");
  const key = useRef(crypto.randomUUID());
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (
      await run(
        `/practice/${p.id}/requests`,
        "POST",
        { target, topic, body, clientKey: key.current },
        "Обращение сохранено",
      )
    ) {
      setBody("");
      key.current = crypto.randomUUID();
    }
  }
  return (
    <>
      <Back go={go} screen={mentorView ? "student" : "home"} />
      <h1>{mentorView ? "Обращения практиканта" : "Мне нужна помощь"}</h1>
      {!mentorView && !closed(p) && (
        <form className="card stack" onSubmit={submit}>
          <Field label="Кому отправить">
            <select value={target} onChange={(e) => setTarget(e.target.value)}>
              <option value="mentor" disabled={!p.mentor}>
                Наставнику
              </option>
              <option value="coordinator">Координатору практики</option>
            </select>
          </Field>
          <Field label="Тема">
            <select value={topic} onChange={(e) => setTopic(e.target.value)}>
              {[
                "Вопрос по задаче",
                "Нет задачи или доступа",
                "Встреча: тема или перенос",
                "Сложности в команде",
                "График и документы",
                "Продолжение работы",
              ].map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
          </Field>
          <Field label="Что случилось и какая помощь нужна?">
            <textarea
              required
              maxLength={2000}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
          <p className="small muted">
            Получатель:{" "}
            {target === "mentor"
              ? p.mentor?.name
              : p.coordinator?.name || "Координатор практики"}
            . Обращение сохранится в системе; внешнее сообщение не отправляется.
          </p>
          <Button disabled={busy} type="submit">
            Отправить обращение
          </Button>
        </form>
      )}
      <h2>{mentorView ? "Вопросы к тебе" : "Мои обращения"}</h2>
      {!p.requests.length && <Empty>Обращений пока нет.</Empty>}
      {p.requests.map((r) => (
        <div className="card stack" key={r.id}>
          <Status>{requestLabels[r.status]}</Status>
          <h2>{r.topic}</h2>
          <p className="small muted">
            {date(r.created)} ·{" "}
            {r.target === "mentor" ? "Наставник" : "Координатор"}
          </p>
          <p className="p-prewrap">{r.body}</p>
          {r.response && <div className="p-note p-prewrap">{r.response}</div>}
          {mentorView && !closed(p) && <RequestReply {...props} request={r} />}
        </div>
      ))}
    </>
  );
}
function RequestReply({
  p,
  request: r,
  run,
  busy,
}: Props & { request: HelpRequest }) {
  const [response, setResponse] = useState(r.response),
    [status, setStatus] = useState(r.status);
  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        void run(
          `/practice/${p.id}/requests/${r.id}`,
          "PATCH",
          { status, response, version: r.version },
          "Ответ сохранён",
        );
      }}
    >
      <Field label="Ответ практиканту">
        <textarea
          required={status === "resolved"}
          maxLength={2000}
          value={response}
          onChange={(e) => setResponse(e.target.value)}
        />
      </Field>
      <Field label="Статус">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value as HelpRequest["status"])}
        >
          {Object.entries(requestLabels).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </Field>
      <Button disabled={busy} secondary type="submit">
        Сохранить ответ
      </Button>
    </form>
  );
}
function Career({ p, go, run, busy, mentorView }: Props) {
  const [interested, setInterested] = useState(p.career?.interested !== 0),
    [direction, setDirection] = useState(p.career?.direction ?? p.title),
    [schedule, setSchedule] = useState(p.career?.schedule ?? ""),
    [comment, setComment] = useState(p.career?.comment ?? "");
  if (mentorView)
    return (
      <Empty>Карьерные предпочтения практиканта доступны координатору.</Empty>
    );
  return (
    <>
      <Back go={go} />
      <h1>Остаться в Очаково</h1>
      <div className="hero stack">
        <h2>ПРОДОЛЖИМ ВМЕСТЕ?</h2>
        <p>Обсудим интересы, учёбу и возможности продолжить работу.</p>
      </div>
      <ol className="p-steps">
        <li>Расскажи, что тебе интересно и какой график подходит.</li>
        <li>Координатор уточнит реальные вакансии и следующий шаг.</li>
        <li>Вы обсудите условия и примете решение.</li>
      </ol>
      <p className="small muted">
        Интерес к работе не гарантирует наличие вакансии или предложение.
      </p>
      <form
        className="card stack"
        onSubmit={(e) => {
          e.preventDefault();
          void run(
            `/practice/${p.id}/career`,
            "PUT",
            { interested, direction, schedule, comment },
            "Предпочтения сохранены для координатора",
          );
        }}
      >
        <label className="p-check">
          <input
            type="checkbox"
            checked={interested}
            onChange={(e) => setInterested(e.target.checked)}
          />
          <span>Хочу обсудить продолжение работы</span>
        </label>
        <Field label="Интересующее направление">
          <input
            maxLength={300}
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
          />
        </Field>
        <Field label="Какой график подходит с учётом учёбы?">
          <textarea
            maxLength={500}
            value={schedule}
            onChange={(e) => setSchedule(e.target.value)}
          />
        </Field>
        <Field label="Комментарий · Необязательно">
          <textarea
            maxLength={2000}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
        </Field>
        <Button disabled={busy || closed(p)} type="submit">
          Сохранить предпочтения
        </Button>
        {p.career && (
          <p className="small muted">
            Последнее обновление: {date(p.career.created)}
          </p>
        )}
      </form>
      <Button secondary onClick={() => go("help")}>
        Задать вопрос координатору
      </Button>
    </>
  );
}
function Results(props: Props) {
  const { p, go, run, busy, mentorView } = props;
  const [body, setBody] = useState("");
  const key = useRef(crypto.randomUUID());
  function download() {
    const url = URL.createObjectURL(
      new Blob([report(p)], { type: "text/plain;charset=utf-8" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "Результаты практики.txt";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  return (
    <>
      <Back go={go} screen={mentorView ? "student" : "home"} />
      <h1>{mentorView ? "Обратная связь" : "Мои результаты"}</h1>
      <div className="p-note stack">
        <h2>Уже получается</h2>
        <p>
          {p.goals.filter((g) => g.status === "approved").length} из{" "}
          {p.goals.length} целей подтверждены наставником.
        </p>
      </div>
      {p.goals
        .filter((g) => g.status === "approved")
        .map((g) => (
          <Card
            key={g.id}
            title={g.title}
            sub="Подтверждено наставником"
            icon="✓"
            onClick={() => go("goal", g.id)}
          />
        ))}
      <h2>Обратная связь наставника</h2>
      {p.feedback.length ? (
        p.feedback.map((f) => (
          <div className="card stack" key={f.id}>
            <p className="small p-accent">
              {f.author_name} · {date(f.created)}
            </p>
            <p className="p-prewrap">{f.body}</p>
          </div>
        ))
      ) : (
        <Empty>
          Здесь появится обратная связь после обсуждения с наставником.
        </Empty>
      )}
      {mentorView && !closed(p) && (
        <form
          className="card stack"
          onSubmit={async (e) => {
            e.preventDefault();
            if (
              await run(
                `/practice/${p.id}/feedback`,
                "POST",
                { body, clientKey: key.current },
                "Отзыв опубликован",
              )
            ) {
              setBody("");
              key.current = crypto.randomUUID();
            }
          }}
        >
          <Field label="Что получилось и что попробовать дальше?">
            <textarea
              required
              maxLength={4000}
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </Field>
          <Button disabled={busy} type="submit">
            Оставить обратную связь
          </Button>
        </form>
      )}
      <Button secondary onClick={download}>
        Скачать свои результаты
      </Button>
    </>
  );
}
function Finish({ p, go, mentorView }: Props) {
  return (
    <>
      <Back go={go} screen={mentorView ? "student" : "home"} />
      <h1>Завершение практики</h1>
      <div className="p-note stack">
        <h2>{date(p.end_date)} — конец практики</h2>
        <p>Подведём итоги, подготовим документы и обсудим следующий шаг.</p>
      </div>
      <Card
        title="Результаты и обратная связь"
        sub="Цели, навыки и комментарии наставника"
        icon="◎"
        onClick={() => go("results")}
      />
      <h2>Документы для учёбы</h2>
      {p.documents.length ? (
        p.documents.map((d, i) => (
          <div className="card stack" key={i}>
            <h3>{d.title}</h3>
            <Status>{d.status}</Status>
          </div>
        ))
      ) : (
        <Empty>
          Список документов ещё не добавлен. Уточни его у координатора.
        </Empty>
      )}
      <p className="small muted">
        Статусы документов обновляет администратор практики.
      </p>
      {!mentorView && (
        <Button onClick={() => go("career")}>
          Обсудить продолжение работы
        </Button>
      )}
    </>
  );
}
function MentorHome({
  data,
  select,
}: {
  data: PracticeData;
  select: (id: string) => void;
}) {
  const pending = data.mentees
    .flatMap((p) => p.requests)
    .filter((r) => r.status !== "resolved").length;
  return (
    <>
      <h1>Кабинет наставника</h1>
      <p className="muted">
        {data.mentor?.name} · {data.mentor?.position}
      </p>
      <div className="p-grid">
        <div className="card stack">
          <span className="small muted">Закреплённые практиканты</span>
          <strong className="p-stat">{data.mentees.length}</strong>
        </div>
        <div className="card stack">
          <span className="small muted">Ждут ответа</span>
          <strong className="p-stat">{pending} обращений</strong>
        </div>
      </div>
      <h2>Мои практиканты</h2>
      {data.mentees.length ? (
        data.mentees.map((p) => (
          <button
            key={p.id}
            className="card p-mentee stack"
            onClick={() => select(p.id)}
          >
            <div className="p-link-row">
              <h2>{p.studentName}</h2>
              <span aria-hidden="true">→</span>
            </div>
            <p className="small muted">
              {p.title} · {date(p.start_date)} — {date(p.end_date)}
            </p>
            <Status>{practiceLabels[p.status]}</Status>
            <p className="small">
              Цели: {p.goals.filter((g) => g.status === "approved").length} из{" "}
              {p.goals.length} подтверждены · На проверке:{" "}
              {p.goals.filter((g) => g.status === "review").length}
            </p>
          </button>
        ))
      ) : (
        <Empty>Администратор ещё не закрепил за тобой практикантов.</Empty>
      )}
      <div className="p-note">
        Здесь доступны рабочие цели, встречи и обращения, направленные
        наставнику. Личные ответы опросов не отображаются.
      </div>
    </>
  );
}
