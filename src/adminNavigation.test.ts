import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";

test("opening the narrow admin menu survives document resizing, but adapts to viewport width", () => {
  let initialize: (() => void) | undefined;
  const window = {
    innerWidth: 1280,
    theme: () => ({
      sidebarOpen: (() => false) as boolean | (() => boolean),
      sidebarToggle() { this.sidebarOpen = !this.sidebarOpen; },
      themeBindings: {
        "x-resize.window"(this: { sidebarOpen: boolean }) {
          this.sidebarOpen = window.innerWidth > 1280;
        },
      },
    }),
  };
  runInNewContext(
    readFileSync(new URL("../backoffice/static/backoffice/navigation.js", import.meta.url), "utf8"),
    { window, document: { addEventListener: (_: string, handler: () => void) => { initialize = handler; } } },
  );
  assert.ok(initialize);
  initialize();
  const state = window.theme();
  assert.equal(state.sidebarOpen, false);
  state.sidebarToggle();
  assert.equal(state.sidebarOpen, true);
  state.themeBindings["x-resize.window"].call(state as { sidebarOpen: boolean });
  assert.equal(state.sidebarOpen, true);
  window.innerWidth = 1024;
  state.themeBindings["x-resize.window"].call(state as { sidebarOpen: boolean });
  assert.equal(state.sidebarOpen, false);
  window.innerWidth = 1600;
  state.themeBindings["x-resize.window"].call(state as { sidebarOpen: boolean });
  assert.equal(state.sidebarOpen, true);
});
