import { MODEL_LABELS } from "../api";
import { dec, int, ms, pct } from "../lib/format";
import type { EvalSummary, ModelKey, ModelRunState } from "../types";

const ACCENT: Record<ModelKey, { color: string; soft: string; tag: string }> = {
  ai: { color: "var(--color-ai)", soft: "var(--color-ai-soft)", tag: "rules + Gemini" },
  rag: { color: "var(--color-rag)", soft: "var(--color-rag-soft)", tag: "search + Gemini" },
};

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 w-full bg-[var(--color-paper-2)]">
      <div
        className="grow h-full"
        style={{ width: `${Math.max(2, value * 100)}%`, backgroundColor: color }}
      />
    </div>
  );
}

/** Tiny signed comparison against the peer model. Green when this model wins. */
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
    return <span className="tnum text-[10px] text-[var(--color-ink-soft)]">even</span>;
  const better = lowerIsBetter ? mine < peer : mine > peer;
  return (
    <span
      className="tnum text-[10px]"
      style={{ color: better ? "var(--color-good)" : "var(--color-ink-soft)" }}
      title="vs. the other model"
    >
      {better ? "▲" : "▼"} {fmt(Math.abs(diff))}
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
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
          {label}
        </span>
        <span className="flex items-baseline gap-2">
          {delta}
          <span className="tnum text-lg font-semibold text-[var(--color-ink)]">{display}</span>
        </span>
      </div>
      {value !== undefined && <Bar value={value} color={color} />}
      {hint && <span className="text-[11px] text-[var(--color-ink-soft)]">{hint}</span>}
    </div>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-ink-soft)]">
        {children}
      </span>
      <span className="h-px flex-1 bg-[var(--color-line)]" />
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
    <div className="flex flex-col gap-5">
      {/* hero: accuracy leads the card */}
      <div className="flex flex-col gap-2">
        <div className="flex items-end justify-between gap-3">
          <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
            Accuracy
          </span>
          <Delta mine={summary.mean_accuracy_score} peer={peer?.mean_accuracy_score} fmt={pct} />
        </div>
        <div className="flex items-baseline gap-2">
          <span className="tnum font-[family-name:var(--font-display)] text-5xl font-semibold leading-none">
            {pct(summary.mean_accuracy_score)}
          </span>
          <span className="text-[11px] text-[var(--color-ink-soft)]">
            cat {pct(summary.category_accuracy)} · tier {pct(summary.tier_accuracy)}
          </span>
        </div>
        <Bar value={summary.mean_accuracy_score} color={color} />
      </div>

      <SectionLabel>Quality</SectionLabel>
      <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
        <Metric
          label="Confidence"
          display={dec(summary.mean_confidence)}
          value={summary.mean_confidence}
          color={color}
          delta={<Delta mine={summary.mean_confidence} peer={peer?.mean_confidence} fmt={(v) => dec(v)} />}
        />
        <Metric
          label="Explanation quality"
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

      <SectionLabel>Cost &amp; reliability</SectionLabel>
      <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
        <Metric
          label="Fallback rate"
          display={pct(summary.fallback_rate)}
          value={summary.fallback_rate}
          color={color}
          hint={summary.fallback_rate > 0 ? "used backup logic" : "used live AI"}
          delta={
            <Delta mine={summary.fallback_rate} peer={peer?.fallback_rate} lowerIsBetter fmt={pct} />
          }
        />
        <Metric
          label="Tokens (total)"
          display={int(summary.tokens_total)}
          color={color}
          hint={`avg ${dec(summary.avg_tokens_per_match, 0)}/match · in ${int(
            summary.tokens_input_total,
          )} / out ${int(summary.tokens_output_total)}`}
          delta={
            <Delta
              mine={summary.tokens_total}
              peer={peer?.tokens_total}
              lowerIsBetter
              fmt={int}
            />
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
    <section
      className="card card-lift rise relative flex flex-col gap-5 border border-[var(--color-line)] bg-[var(--color-paper)] p-6"
      style={{ borderTopColor: accent.color, borderTopWidth: 4 }}
    >
      <header className="flex items-start justify-between">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-2xl font-semibold leading-none">
            {MODEL_LABELS[model]}
          </h2>
          <span
            className="mt-2 inline-block px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-paper)]"
            style={{ backgroundColor: accent.color }}
          >
            {accent.tag}
          </span>
        </div>
        {state.status === "done" && state.result && (
          <span className="tnum text-[11px] text-[var(--color-ink-soft)]">
            run {state.result.run_id}
          </span>
        )}
      </header>

      {state.status === "idle" && (
        <div className="flex items-center justify-center rounded-sm border border-dashed border-[var(--color-line)] py-12">
          <p className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-ink-soft)]">
            Awaiting run
          </p>
        </div>
      )}

      {state.status === "loading" && (
        <div className="flex flex-col gap-4 py-6" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="sweep relative h-6 overflow-hidden bg-[var(--color-paper-2)]" />
          ))}
          <p className="text-center text-xs uppercase tracking-[0.16em]" style={{ color: accent.color }}>
            evaluating…
          </p>
        </div>
      )}

      {state.status === "error" && (
        <div className="border border-[var(--color-signal)] bg-[color-mix(in_srgb,var(--color-signal)_8%,transparent)] p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-signal)]">
            Run failed
          </p>
          <p className="mt-1.5 font-mono text-xs leading-relaxed text-[var(--color-ink)]">
            {state.error}
          </p>
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
