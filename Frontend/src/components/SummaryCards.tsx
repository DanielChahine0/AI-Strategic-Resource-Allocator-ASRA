import { MODEL_LABELS } from "../api";
import { dec, int, ms, pct } from "../lib/format";
import type { EvalSummary, ModelKey, ModelRunState } from "../types";

const ACCENT: Record<ModelKey, { color: string; tag: string }> = {
  ai: { color: "var(--color-ai)", tag: "rules + Gemini" },
  rag: { color: "var(--color-rag)", tag: "search + Gemini" },
};

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-subtle">
      <div
        className="grow h-full rounded-full"
        style={{ width: `${Math.max(2, value * 100)}%`, backgroundColor: color }}
      />
    </div>
  );
}

/** Tiny signed comparison against the peer model. Sage when this model wins. */
function Delta({
  mine,
  peer,
  lowerIsBetter = false,
  fmt,
}: {
  mine: number;
  peer?: number | null;
  lowerIsBetter?: boolean;
  fmt: (v: number) => string;
}) {
  if (peer === null || peer === undefined) return null;
  const diff = mine - peer;
  if (diff === 0)
    return (
      <span className="tnum rounded-md px-1.5 py-0.5 text-[11px] text-ink-faint">even</span>
    );
  const better = lowerIsBetter ? mine < peer : mine > peer;
  return (
    <span
      className={`tnum rounded-md px-1.5 py-0.5 text-[11px] font-medium ${
        better ? "bg-good-soft text-good" : "bg-signal-soft text-signal"
      }`}
      title="vs. the other model"
    >
      {better ? "↑" : "↓"} {fmt(Math.abs(diff))}
    </span>
  );
}

function Metric({
  label,
  display,
  value,
  color,
  hint,
  delta,
}: {
  label: string;
  display: string;
  value?: number;
  color: string;
  hint?: string;
  delta?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">
          {label}
        </span>
        <span className="flex items-baseline gap-2">
          {delta}
          <span className="tnum text-lg text-ink">{display}</span>
        </span>
      </div>
      {value !== undefined && <Bar value={value} color={color} />}
      {hint && <span className="text-[11px] text-ink-faint">{hint}</span>}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3">
      <span className="font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-ink-faint">
        {children}
      </span>
      <span className="h-px flex-1 bg-line-soft" />
    </div>
  );
}

function Loaded({
  summary,
  color,
  wall,
  peer,
  peerWall,
}: {
  summary: EvalSummary;
  color: string;
  wall: number;
  peer?: EvalSummary | null;
  peerWall?: number | null;
}) {
  return (
    <div className="flex flex-col gap-7">
      {/* hero: accuracy leads the card */}
      <div className="flex flex-col gap-3">
        <div className="flex items-end justify-between gap-3">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-soft">
            Accuracy
          </span>
          <Delta mine={summary.mean_accuracy_score} peer={peer?.mean_accuracy_score} fmt={pct} />
        </div>
        <div className="flex items-baseline gap-3">
          <span className="tnum text-metric text-ink">{pct(summary.mean_accuracy_score)}</span>
          <span className="text-[11px] leading-snug text-ink-faint">
            cat {pct(summary.category_accuracy)} · tier {pct(summary.tier_accuracy)}
            <br />
            over {summary.n_scored} labelled
            {summary.error_count > 0 ? ` · ${summary.error_count} unserved` : ""}
          </span>
        </div>
        <Bar value={summary.mean_accuracy_score} color={color} />
      </div>

      <div className="flex flex-col gap-4">
        <SectionLabel>Quality</SectionLabel>
        <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
          <Metric
            label="Confidence"
            display={dec(summary.mean_confidence)}
            value={summary.mean_confidence}
            color={color}
            delta={
              <Delta mine={summary.mean_confidence} peer={peer?.mean_confidence} fmt={(v) => dec(v)} />
            }
          />
          <Metric
            label="Explanation"
            display={dec(summary.mean_explanation_quality)}
            value={summary.mean_explanation_quality}
            color={color}
            delta={
              <Delta
                mine={summary.mean_explanation_quality}
                peer={peer?.mean_explanation_quality}
                fmt={(v) => dec(v)}
              />
            }
          />
        </div>
      </div>

      <div className="flex flex-col gap-4">
        <SectionLabel>Cost &amp; reliability</SectionLabel>
        <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
          <Metric
            label="Fallback"
            display={pct(summary.fallback_rate)}
            value={summary.fallback_rate}
            color={color}
            hint={summary.fallback_rate > 0 ? "used backup logic" : "used live AI"}
            delta={
              <Delta mine={summary.fallback_rate} peer={peer?.fallback_rate} lowerIsBetter fmt={pct} />
            }
          />
          <Metric
            label="Tokens"
            display={int(summary.tokens_total)}
            color={color}
            hint={`avg ${dec(summary.avg_tokens_per_match, 0)}/match`}
            delta={
              <Delta mine={summary.tokens_total} peer={peer?.tokens_total} lowerIsBetter fmt={int} />
            }
          />
          <Metric
            label="Wall time"
            display={ms(wall)}
            color={color}
            hint={`${summary.n} applicants · ${summary.error_count} errors`}
            delta={
              peerWall !== null && peerWall !== undefined ? (
                <Delta mine={wall} peer={peerWall} lowerIsBetter fmt={ms} />
              ) : undefined
            }
          />
        </div>
      </div>
    </div>
  );
}

export default function SummaryCard({
  model,
  state,
  peer,
}: {
  model: ModelKey;
  state: ModelRunState;
  peer?: ModelRunState;
}) {
  const accent = ACCENT[model];
  const peerSummary = peer?.status === "done" ? peer.result?.summary : null;
  const peerWall = peer?.status === "done" ? peer.result?.wall_time_ms : null;
  return (
    <section className="card card-lift rise flex flex-col gap-7 rounded-card border border-line bg-surface p-7">
      <header className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className="mt-1 h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: accent.color }}
            aria-hidden
          />
          <div className="flex flex-col">
            <h2 className="font-display text-title leading-none text-ink">
              {MODEL_LABELS[model]}
            </h2>
            <span className="mt-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-ink-faint">
              {accent.tag}
            </span>
          </div>
        </div>
        {state.status === "done" && state.result && (
          <span className="tnum text-[11px] text-ink-faint">{state.result.run_id}</span>
        )}
      </header>

      {state.status === "idle" && (
        <div className="flex items-center justify-center rounded-xl border border-dashed border-line py-14">
          <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">
            Awaiting run
          </p>
        </div>
      )}

      {state.status === "loading" && (
        <div className="flex flex-col gap-4 py-6" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="sweep h-6 rounded-lg bg-subtle" />
          ))}
          <p
            className="text-center font-mono text-[11px] uppercase tracking-[0.18em]"
            style={{ color: accent.color }}
          >
            evaluating…
          </p>
        </div>
      )}

      {state.status === "error" && (
        <div className="rounded-xl border border-signal/40 bg-signal-soft/60 p-4">
          <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-signal">
            Run failed
          </p>
          <p className="mt-1.5 font-mono text-xs leading-relaxed text-ink">{state.error}</p>
        </div>
      )}

      {state.status === "done" && state.result && (
        <Loaded
          summary={state.result.summary}
          color={accent.color}
          wall={state.result.wall_time_ms}
          peer={peerSummary}
          peerWall={peerWall}
        />
      )}
    </section>
  );
}
