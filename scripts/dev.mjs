import { spawn } from "node:child_process";
import { setTimeout } from "node:timers/promises";

const api = spawn(
  "python3",
  ["-m", "server", "--host", "127.0.0.1", "--port", "3001"],
  {
    stdio: "inherit",
    env: {
      ...process.env,
      DEV_AUTH: process.env.DEV_AUTH ?? "1",
      ALLOWED_ORIGINS: [
        process.env.ALLOWED_ORIGINS,
        "http://127.0.0.1:5188",
        "http://localhost:5188",
      ]
        .filter(Boolean)
        .join(","),
    },
  },
);
let stopping = false;
let frontend;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  frontend?.kill("SIGTERM");
  api.kill("SIGTERM");
  process.exitCode = code;
}
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
api.on("exit", (code) => stop(code ?? 1));
api.on("error", () => stop(1));
for (let attempt = 0; attempt < 40 && !stopping; attempt++) {
  try {
    const response = await fetch("http://127.0.0.1:3001/api/catalog");
    if (response.ok) break;
  } catch {
    /* Wait for the Python server to bind. */
  }
  await setTimeout(150);
}
if (!stopping) {
  frontend = spawn(
    process.execPath,
    ["node_modules/vite/bin/vite.js", "--host", "127.0.0.1"],
    { stdio: "inherit" },
  );
  frontend.on("exit", (code) => stop(code ?? 1));
  frontend.on("error", () => stop(1));
}
