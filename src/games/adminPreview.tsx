import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/inter";
import "../styles.css";
import { GamePlayer } from "./Games";
import { loadSpriteAssets } from "./sprites";
import type { CompletionResult, Task } from "./types";

function Preview() {
  const [task, setTask] = useState<Task>();
  const [draft, setDraft] = useState<unknown>({});
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const id = new URLSearchParams(location.search).get("level") || "";
  const base = "/admin/content/leveldefinition/" + encodeURIComponent(id);
  useEffect(() => {
    let live = true;
    void Promise.all([
      loadSpriteAssets(),
      fetch(base + "/preview-data/", { credentials: "same-origin" }).then(
        async (r) => {
          const body = await r.json();
          if (!r.ok)
            throw new Error(body.message || "Нет доступа к предпросмотру.");
          return body.task as Task;
        },
      ),
    ])
      .then(([, value]) => {
        if (live) setTask(value);
      })
      .catch((e) => {
        if (live)
          setError(e instanceof Error ? e.message : "Предпросмотр недоступен.");
      });
    return () => {
      live = false;
    };
  }, [base]);
  async function complete(solution: unknown): Promise<CompletionResult> {
    const csrf =
      document.cookie
        .split("; ")
        .find((s) => s.startsWith("csrftoken="))
        ?.split("=")[1] || "";
    const response = await fetch(base + "/preview-check/", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": decodeURIComponent(csrf),
      },
      body: JSON.stringify({ solution }),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.message || "Проверка недоступна.");
    return body as CompletionResult;
  }
  return (
    <main className="app-shell app-shell-game">
      {error ? (
        <p role="alert">{error}</p>
      ) : !task ? (
        <p>Загружаем предпросмотр…</p>
      ) : (
        <GamePlayer
          task={task}
          draft={draft}
          onSave={async (value) => {
            setDraft(value);
          }}
          onComplete={complete}
          onCareer={() =>
            setMessage("Карьерный переход доступен в мини-приложении.")
          }
          onExit={() => {
            location.href = base + "/change/";
          }}
        />
      )}
      {message && <p role="status">{message}</p>}
    </main>
  );
}
createRoot(document.getElementById("root")!).render(<Preview />);
