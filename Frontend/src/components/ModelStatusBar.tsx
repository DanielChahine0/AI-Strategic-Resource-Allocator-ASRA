import { useEffect, useRef, useState } from "react";
import { fetchStatus, MODEL_LABELS } from "../api";
import type { ModelKey, ModelStateName, ModelStatus } from "../types";

const ACCENT: Record<ModelKey, string> = {
  ai: "var(--color-ai)",
  rag: "var(--color-rag)",
};

// A colour + short label for each derived state. "live" is the only green.
const STATE_STYLE: Record<ModelStateName, { color: string; label: string }> = {
  live: { color: "var(--color-ink)", label: "Live" },
  ready: { color: "var(--color-ink-faint)", label: "Ready" },
  rate_limited: { color: "var(--color-signal)", label: "Rate-limited" },
  auth_error: { color: "var(--color-signal)", label: "Auth error" },
  no_api_key: { color: "var(--color-ink-faint)", label: "No API key" },
  sdk_missing: { color: "var(--color-signal)", label: "SDK missing" },
  degraded: { color: "var(--color-signal)", label: "Degraded" },
};

const POLL_MS = 15_000;

type Cell =
  | { kind: "loading" }
  | { kind: "unreachable"; error: string }
  | { kind: "ok"; status: ModelStatus; fetchedAt: number };

function fmtCountdown(secs: number): string {
  if (secs <= 0) return "now";
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return s ? `${m}m ${s}s` : `${m}m`;
}

function StatusRow({ model, cell, now }: { model: ModelKey; cell: Cell; now: number }) {
  const accent = ACCENT[model];

  let dotColor = "var(--color-ink-faint)";
  let label = "n/a";
  let extra: React.ReactNode = null;

  if (cell.kind === "loading") {
    label = "Checking…";
  } else if (cell.kind === "unreachable") {
    dotColor = "var(--color-signal)";
    label = "Offline";
  } else {
    const s = cell.status;
    const style = STATE_STYLE[s.state] ?? STATE_STYLE.degraded;
    dotColor = style.color;
    label = style.label;

    if (s.state === "rate_limited" && s.retry_after_seconds != null) {
      // Tick the server's retry window down locally between polls.
      const elapsed = Math.floor((now - cell.fetchedAt) / 1000);
      const remaining = Math.max(0, s.retry_after_seconds - elapsed);
      extra = `retry ${fmtCountdown(remaining)}`;
    } else if (s.session.total_calls > 0) {
      extra = `${s.session.successes}/${s.session.total_calls}`;
    }
  }

  return (
    <div className="flex items-center gap-2.5">
      <span
        className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
        style={{ backgroundColor: dotColor }}
        aria-hidden
      />
      <span
        className="font-mono text-[11px] font-medium uppercase tracking-[0.2em]"
        style={{ color: accent }}
      >
        {MODEL_LABELS[model].replace(" Model", "")}
      </span>
      <span className="text-[13px]" style={{ color: dotColor }}>
        {label}
      </span>
      {extra && <span className="tnum text-xs text-ink-faint">· {extra}</span>}
    </div>
  );
}

/**
 * Live model health strip. Polls each backend's /status every 15s with a
 * zero-cost snapshot (no probe, so no quota spend) and shows whether each model
 * is giving live Gemini answers or running on backup logic.
 */
export default function ModelStatusBar() {
  const [ai, setAi] = useState<Cell>({ kind: "loading" });
  const [rag, setRag] = useState<Cell>({ kind: "loading" });
  const [now, setNow] = useState(() => Date.now());
  const timers = useRef<number[]>([]);

  useEffect(() => {
    let cancelled = false;
    const setters: Record<ModelKey, (c: Cell) => void> = { ai: setAi, rag: setRag };

    async function poll(model: ModelKey) {
      try {
        const status = await fetchStatus(model);
        if (!cancelled) setters[model]({ kind: "ok", status, fetchedAt: Date.now() });
      } catch (e) {
        if (!cancelled)
          setters[model]({ kind: "unreachable", error: (e as Error).message });
      }
    }

    (["ai", "rag"] as ModelKey[]).forEach(poll);
    const pollId = window.setInterval(() => {
      (["ai", "rag"] as ModelKey[]).forEach(poll);
    }, POLL_MS);
    // Local 1s ticker so rate-limit countdowns feel live between polls.
    const tickId = window.setInterval(() => setNow(Date.now()), 1000);
    timers.current = [pollId, tickId];

    return () => {
      cancelled = true;
      timers.current.forEach(window.clearInterval);
    };
  }, []);

  return (
    <section
      className="mt-10 flex flex-wrap items-center gap-x-8 gap-y-2 border-y border-line py-3.5"
      aria-label="Model status"
    >
      <StatusRow model="ai" cell={ai} now={now} />
      <span className="hidden h-3.5 w-px bg-line sm:block" aria-hidden />
      <StatusRow model="rag" cell={rag} now={now} />
      <span className="w-full text-right font-mono text-[11px] uppercase tracking-[0.18em] text-ink-faint sm:ml-auto sm:w-auto">
        every 15s
      </span>
    </section>
  );
}
