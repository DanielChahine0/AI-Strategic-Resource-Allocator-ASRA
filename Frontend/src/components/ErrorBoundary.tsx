import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches render-time exceptions anywhere in the tree so a single bad response
 * (e.g. a malformed `/evaluate` body that throws inside a formatter or a row
 * accessor) degrades to a readable panel instead of a blank white screen.
 *
 * The per-model `try/catch` in App.tsx only handles *rejected fetches*; it does
 * nothing for exceptions thrown during render, which React only surfaces to an
 * error boundary. Without this, one model's malformed payload takes down both
 * panels and the whole page.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Surface for debugging; a production build would forward this to an
    // error-reporting service instead of the console.
    console.error("Uncaught render error:", error, info.componentStack);
  }

  private reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="mx-auto max-w-2xl px-6 py-24">
        <div className="rounded-card border border-signal/40 bg-signal-soft/50 p-8">
          <h1 className="font-display text-display text-ink">Something broke while rendering</h1>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-ink-soft">
            Usually a malformed response from one of the backends. Try again; if it persists,
            check the backend logs.
          </p>
          <pre className="mt-5 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line bg-subtle p-3.5 font-mono text-[11px] text-ink">
            {error.message}
          </pre>
          <button
            onClick={this.reset}
            className="mt-5 rounded-lg bg-ink px-5 py-2 text-[13px] font-medium text-canvas transition-colors hover:bg-ink/90"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }
}
