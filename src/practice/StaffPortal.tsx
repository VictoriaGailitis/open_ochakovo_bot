import { useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  clearStaffSession,
  loginStaff,
  staffApi,
  type StaffRole,
} from "../api";
import { PracticeApp } from "./PracticeApp";
import { CommunityApp } from "../community/CommunityApp";
import { staffDestination, staffHome } from "../community/staffRoutes";
import { Mascot } from "../components/Art";
import "./practice.css";

export function StaffPortal({ page }: { page: string }) {
  const [checking, setChecking] = useState(page !== "login");
  const [allowed, setAllowed] = useState(false);
  const [role, setRole] = useState<StaffRole | null>(null);
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    setAllowed(false);
    setError("");
    if (page === "login") {
      setChecking(false);
      return;
    }
    setChecking(true);
    void staffApi<{ role: StaffRole }>("/staff/session")
      .then((result) => {
        if (!alive) return;
        setRole(result.role);
        const target = staffDestination(result.role, page);
        if (page !== target) location.hash = "/" + target;
        else setAllowed(true);
      })
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 401) {
          clearStaffSession();
          location.hash = "/login";
        } else {
          setError(
            e instanceof Error ? e.message : "Не удалось проверить вход.",
          );
        }
      })
      .finally(() => {
        if (alive) setChecking(false);
      });
    return () => {
      alive = false;
    };
  }, [page]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const role = await loginStaff(login, password);
      setRole(role);
      setPassword("");
      const target = staffHome(role);
      if (page === target) setAllowed(true);
      else location.hash = "/" + target;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось войти.");
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    try {
      await staffApi("/auth", "DELETE");
    } catch {
      // Clear the local session even when the server is unavailable.
    } finally {
      clearStaffSession();
      location.hash = "/login";
    }
  }

  if (page !== "login" && allowed && role) {
    if (page === "community" || page === "employee")
      return <CommunityApp role={role} onLogout={logout} />;
    return <PracticeApp onLogout={logout} />;
  }
  return (
    <div className="app-shell p-shell">
      <header className="app-header">
        <a href="#/home" className="brand">
          Очаково: изнутри
        </a>
      </header>
      <main className="screen stack">
        <a className="p-return" href="#/home">
          ← На главную
        </a>
        <h1>Я уже в Очаково</h1>
        {checking ? (
          <p role="status">Проверяем вход…</p>
        ) : (
          <>
            <p className="muted">
              Вход для сотрудников, практикантов и наставников
            </p>
            <div className="p-login-mascot">
              <Mascot />
            </div>
            <form className="card stack" onSubmit={submit}>
              <p className="small muted">
                Введи логин и пароль, которые тебе прислали на почту.
              </p>
              <label className="p-field">
                <span>Логин</span>
                <input
                  name="username"
                  autoComplete="username"
                  required
                  maxLength={120}
                  value={login}
                  onChange={(e) => setLogin(e.target.value)}
                  autoCapitalize="none"
                  spellCheck={false}
                />
              </label>
              <label className="p-field">
                <span>Пароль</span>
                <input
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                  maxLength={256}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              {error && (
                <p className="error" role="alert">
                  {error}
                </p>
              )}
              <button
                className="button button-primary"
                disabled={busy}
                type="submit"
              >
                {busy ? "Входим…" : "Войти"}
              </button>
            </form>
            <p className="small muted">
              Если данные для входа ещё не пришли или пароль не подходит,
              обратись к координатору или сотруднику, который помогает тебе с
              доступом.
            </p>
          </>
        )}
      </main>
    </div>
  );
}
