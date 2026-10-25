/* Normalize Unfold's responsive initial state before Alpine initializes it.
 * In Unfold 0.110, sidebarOpen starts as a method; negating that method on the
 * first mobile click closes the menu instead of opening it.
 */
document.addEventListener("alpine:init", () => {
  const createTheme = window.theme;
  if (typeof createTheme !== "function") return;
  window.theme = function (...args) {
    const state = createTheme.apply(this, args);
    if (typeof state.sidebarOpen === "function") {
      state.sidebarOpen = state.sidebarOpen();
    }
    // Unfold's resize plugin observes the whole document, including changes
    // in height caused by opening the menu. Only a viewport-width change
    // should reset its responsive state.
    const resize = state.themeBindings?.["x-resize.window"];
    let width = window.innerWidth;
    if (typeof resize === "function") {
      state.themeBindings["x-resize.window"] = function (...resizeArgs) {
        if (width === window.innerWidth) return;
        width = window.innerWidth;
        return resize.apply(this, resizeArgs);
      };
    }
    return state;
  };
}, { once: true });
