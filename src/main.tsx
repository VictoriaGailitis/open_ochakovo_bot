import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "@fontsource-variable/inter";
import "./styles.css";

class ErrorBoundary extends React.Component<
  React.PropsWithChildren,
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main className="app-shell screen stack">
        <h1>Не удалось открыть экран</h1>
        <p>Твой сохранённый прогресс остался на сервере.</p>
        <button
          className="button button-primary"
          onClick={() => {
            window.location.hash = "";
            window.location.reload();
          }}
        >
          Открыть заново
        </button>
      </main>
    ) : (
      this.props.children
    );
  }
}

const root: ReactDOM.Root =
  import.meta.hot?.data.root ??
  ReactDOM.createRoot(document.getElementById("root")!);
if (import.meta.hot) import.meta.hot.data.root = root;
root.render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
);
