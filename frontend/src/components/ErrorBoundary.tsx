import { Component, type ErrorInfo, type ReactNode } from "react";
import { useI18n } from "../i18n";

// Translated fallback. Separate functional component so it can use the i18n hook (a class can't);
// it sits under <LangProvider> in main.tsx, so translation is available even mid-crash.
function ErrorBoundaryFallback({ error }: { error: Error }) {
  const { t } = useI18n();
  return (
    <div className="centered error-screen">
      <h2 className="error-title">{t("error_boundary_title")}</h2>
      <p className="muted">{t("error_boundary_body")}</p>
      {error.message && <p className="error-detail muted small">{error.message}</p>}
      <div className="error-actions">
        <button className="btn btn-accent" onClick={() => window.location.reload()}>
          {t("reload")}
        </button>
      </div>
    </div>
  );
}

interface State {
  error: Error | null;
}

// Catches render-time errors anywhere in the tree so an unexpected exception shows a recoverable
// "something went wrong" screen with a Reload, instead of React unmounting everything to a blank
// window (issue #70). Query/network errors are handled per-view via <ErrorState>; this is the
// last-resort net for programmer errors / unexpected throws.
export default class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // surface to the console (forwarded to the shell log in the packaged app) for diagnosis
    console.error("[error-boundary] render error:", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return <ErrorBoundaryFallback error={this.state.error} />;
    }
    return this.props.children;
  }
}
