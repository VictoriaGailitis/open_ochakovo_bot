import { test } from "node:test";
import assert from "node:assert/strict";
import { initialize, loadCandidateMedia, loadStaffMedia } from "../api";
import { sessionStore } from "../storage";

test("protected media uses the selected account credential in a header, never in its URL", async () => {
  const originalFetch = globalThis.fetch;
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window");
  const originalLocation = Object.getOwnPropertyDescriptor(
    globalThis,
    "location",
  );
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  };
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { localStorage: storage, sessionStorage: storage },
  });
  Object.defineProperty(globalThis, "location", {
    configurable: true,
    value: { search: "", hash: "" },
  });
  const mediaRequests: { url: string; authorization: string | null }[] = [];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url === "/api/auth")
      return Response.json({
        token: "candidate-test-token",
        mode: "demo",
        userId: "demo-test",
      });
    if (url === "/api/bootstrap") return Response.json({ progress: [] });
    mediaRequests.push({
      url,
      authorization: new Headers(init?.headers).get("Authorization"),
    });
    return new Response(new Uint8Array([0, 1, 2]), {
      headers: { "Content-Type": "video/mp4" },
    });
  };
  try {
    sessionStore.set("ochakovo:staff:session", "staff-test-token");
    await initialize();
    const staffBlob = await loadStaffMedia("team-video");
    const candidateBlob = await loadCandidateMedia("company-video");
    assert.equal(staffBlob.type, "video/mp4");
    assert.equal(candidateBlob.size, 3);
    assert.deepEqual(mediaRequests, [
      {
        url: "/api/media/team-video",
        authorization: "Bearer staff-test-token",
      },
      {
        url: "/api/media/company-video",
        authorization: "Bearer candidate-test-token",
      },
    ]);
    for (const request of mediaRequests) {
      assert.ok(!request.url.includes("token"));
      assert.ok(!request.url.includes("?"));
    }
  } finally {
    globalThis.fetch = originalFetch;
    sessionStore.remove("ochakovo:staff:session");
    if (originalWindow)
      Object.defineProperty(globalThis, "window", originalWindow);
    else Reflect.deleteProperty(globalThis, "window");
    if (originalLocation)
      Object.defineProperty(globalThis, "location", originalLocation);
    else Reflect.deleteProperty(globalThis, "location");
  }
});
