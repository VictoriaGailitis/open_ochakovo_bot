// VK can run in an iframe where browser storage is disabled. Saved application
// data lives on the server; these preferences must never prevent the UI opening.
function storage(kind: "localStorage" | "sessionStorage") {
  const fallback = new Map<string, string>();
  return {
    get(key: string) {
      try {
        return window[kind].getItem(key) ?? fallback.get(key) ?? null;
      } catch {
        return fallback.get(key) ?? null;
      }
    },
    set(key: string, value: string) {
      fallback.set(key, value);
      try {
        window[kind].setItem(key, value);
      } catch {
        /* Ephemeral preference. */
      }
    },
    remove(key: string) {
      fallback.delete(key);
      try {
        window[kind].removeItem(key);
      } catch {
        /* Already removed in memory. */
      }
    },
  };
}
export const localStore = storage("localStorage");
export const sessionStore = storage("sessionStorage");
