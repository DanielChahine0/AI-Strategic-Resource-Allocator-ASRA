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
      <div className="mx-auto max-w-2xl px-6 py-16">
        <div className="border border-[var(--color-signal)] bg-[color-mix(in_srgb,var(--color-signal)_8%,transparent)] p-6">
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-[var(--color-ink)]">
            Something broke while rendering
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-[var(--color-ink-soft)]">
            The page hit an unexpected error — usually a malformed response from
            one of the backends. Try again; if it keeps happening, check the
            backend logs.
          </p>
          <pre className="mt-4 overflow-auto whitespace-pre-wrap break-words border border-[var(--color-line)] bg-[var(--color-paper-2)] p-3 font-mono text-[11px] text-[var(--color-ink)]">
            {error.message}
          </pre>
          <button
            onClick={this.reset}
            className="mt-4 border border-[var(--color-ink)] px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-ink)] transition-colors hover:bg-[var(--color-ink)] hover:text-[var(--color-paper)]"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }
}
