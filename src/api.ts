import bridge from "@vkontakte/vk-bridge";
import type { Bootstrap } from "./types";
import { syncDraftClock } from "./draftClock";
import { localStore, sessionStore } from "./storage";

let token = "";
export type ApiClient = <T>(
  path: string,
  method?: string,
  body?: unknown,
) => Promise<T>;
export type MediaLoader = (id: string) => Promise<Blob>;
export type StaffRole = "intern" | "mentor" | "employee";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public details?: Record<string, string>,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
    keepalive: method === "PUT" && path.endsWith("/draft"),
  });
  const value = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      value?.error?.message ??
        value?.error ??
        value?.message ??
        "Сервер недоступен. Попробуй ещё раз.",
      response.status,
      value?.code,
      value?.details,
    );
  return value as T;
}
function demoId() {
  const key = "ochakovo:demo-user:v1";
  let id = localStore.get(key);
  if (!id) {
    id = "demo-" + crypto.randomUUID();
    localStore.set(key, id);
  }
  return id;
}
const STAFF_SESSION_KEY = "ochakovo:staff:session";
export function clearStaffSession() {
  sessionStore.remove(STAFF_SESSION_KEY);
}
export async function staffApi<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await fetch("/api" + path, {
    method,
    headers: {
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
      Authorization: "Bearer " + (sessionStore.get(STAFF_SESSION_KEY) ?? ""),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store",
  });
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && path !== "/staff/login") {
      clearStaffSession();
      location.hash = "/login";
    }
    throw new ApiError(
      result?.error?.message ??
        result?.error ??
        "Не удалось подключиться. Попробуй ещё раз.",
      response.status,
      result?.code,
    );
  }
  return result as T;
}
export async function loginStaff(login: string, password: string) {
  const result = await staffApi<{ token: string; role: StaffRole }>(
    "/staff/login",
    "POST",
    { login, password },
  );
  sessionStore.set(STAFF_SESSION_KEY, result.token);
  return result.role;
}
async function loadMedia(
  id: string,
  credential: string,
  staff: boolean,
): Promise<Blob> {
  if (!id.trim()) throw new Error("Файл не найден.");
  // Media credentials follow the JSON API boundary: never put a token in a URL.
  const response = await fetch("/api/media/" + encodeURIComponent(id), {
    headers: { Authorization: "Bearer " + credential },
    cache: "no-store",
  });
  if (!response.ok) {
    if (staff && response.status === 401) {
      clearStaffSession();
      location.hash = "/login";
    }
    const result = await response.json().catch(() => null);
    throw new ApiError(
      result?.error?.message ?? result?.error ?? "Не удалось загрузить файл.",
      response.status,
      result?.code,
    );
  }
  return response.blob();
}
export const loadStaffMedia: MediaLoader = (id) =>
  loadMedia(id, sessionStore.get(STAFF_SESSION_KEY) ?? "", true);
export const loadCandidateMedia: MediaLoader = (id) =>
  loadMedia(id, token, false);
export async function initialize(): Promise<{
  data: Bootstrap;
  mode: string;
  vkName?: string;
}> {
  const params = new URLSearchParams(location.search);
  const inVK = params.has("vk_user_id");
  let vkName: string | undefined;
  if (inVK) {
    await Promise.race([
      bridge.send("VKWebAppInit"),
      new Promise((_, reject) =>
        window.setTimeout(
          () => reject(new Error("VK не ответил. Открой приложение заново.")),
          12000,
        ),
      ),
    ]);
  }
  const session = await api<{ token: string; userId: string; mode: string }>(
    "/auth",
    "POST",
    inVK ? { launchParams: location.search.slice(1) } : { devUserId: demoId() },
  );
  token = session.token;
  if (inVK) {
    // Profile fields remain editable; signed launch parameters establish identity server-side.
    const user = await Promise.race([
      bridge.send("VKWebAppGetUserInfo").catch(() => null),
      new Promise<null>((resolve) => setTimeout(() => resolve(null), 3000)),
    ]);
    if (user && "first_name" in user)
      vkName = `${user.first_name} ${user.last_name}`;
  }
  const data = await api<Bootstrap>("/bootstrap");
  syncDraftClock(data.progress.map((p) => p.revision ?? p.draft_revision ?? 0));
  return { data, mode: session.mode, vkName };
}
export async function requestNotifications() {
  if (!new URLSearchParams(location.search).has("vk_user_id"))
    throw new Error("Уведомления доступны при открытии внутри VK.");
  await bridge.send("VKWebAppAllowNotifications");
}
