import { MODEL_LABELS } from "../api";
import { dec, int, ms, pct } from "../lib/format";
import type { EvalSummary, ModelKey, ModelRunState } from "../types";

const ACCENT: Record<ModelKey, { color: string; soft: string; tag: string }> = {
  ai: { color: "var(--color-ai)", soft: "var(--color-ai-soft)", tag: "deterministic + Gemini" },
  rag: { color: "var(--color-rag)", soft: "var(--color-rag-soft)", tag: "retrieval-augmented" },
};

function Bar({ value, color }: { value: number; color: string }) {
  return (
    <div className="h-1.5 w-full bg-[var(--color-paper-2)]">
      <div
        className="h-full transition-[width] duration-700 ease-out"
        style={{ width: `${Math.max(2, value * 100)}%`, backgroundColor: color }}
      />
    </div>
  );
}

function Metric({
  label,
  display,
  value,
  color,
  hint,
}: {
  label: string;
  display: string;
  value?: number;
  color: string;
  hint?: string;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
          {label}
        </span>
        <span className="tnum text-lg font-semibold text-[var(--color-ink)]">{display}</span>
      </div>
      {value !== undefined && <Bar value={value} color={color} />}
      {hint && <span className="text-[11px] text-[var(--color-ink-soft)]">{hint}</span>}
    </div>
  );
}

function Loaded({ summary, color, wall }: { summary: EvalSummary; color: string; wall: number }) {
  return (
    <div className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
      <Metric
        label="Accuracy"
        display={pct(summary.mean_accuracy_score)}
        value={summary.mean_accuracy_score}
        color={color}
        hint={`category ${pct(summary.category_accuracy)} · tier ${pct(summary.tier_accuracy)}`}
      />
      <Metric
        label="Confidence"
        display={dec(summary.mean_confidence)}
        value={summary.mean_confidence}
        color={color}
      />
      <Metric
        label="Explanation quality"
        display={dec(summary.mean_explanation_quality)}
        value={summary.mean_explanation_quality}
        color={color}
      />
      <Metric
        label="Fallback rate"
        display={pct(summary.fallback_rate)}
        value={summary.fallback_rate}
        color={color}
        hint={summary.fallback_rate > 0 ? "no live key → deterministic path" : "live engine"}
      />
      <Metric
        label="Tokens (total)"
        display={int(summary.tokens_total)}
        color={color}
        hint={`avg ${dec(summary.avg_tokens_per_match, 0)}/match · in ${int(
          summary.tokens_input_total,
        )} / out ${int(summary.tokens_output_total)}`}
      />
      <Metric
        label="Wall time"
        display={ms(wall)}
        color={color}
        hint={`${summary.n} applicants · ${summary.error_count} errors`}
      />
    </div>
  );
}

export default function SummaryCard({ model, state }: { model: ModelKey; state: ModelRunState }) {
  const accent = ACCENT[model];
  return (
    <section
      className="rise relative flex flex-col gap-5 border border-[var(--color-line)] bg-[var(--color-paper)] p-6"
      style={{ borderTopColor: accent.color, borderTopWidth: 4 }}
    >
      <header className="flex items-start justify-between">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-2xl font-semibold leading-none">
            {MODEL_LABELS[model]}
          </h2>
          <p className="mt-1.5 text-[11px] uppercase tracking-[0.16em]" style={{ color: accent.color }}>
            {accent.tag}
          </p>
        </div>
        {state.status === "done" && state.result && (
          <span className="tnum text-[11px] text-[var(--color-ink-soft)]">
            run {state.result.run_id}
          </span>
        )}
      </header>

      {state.status === "idle" && (
        <p className="py-8 text-center text-sm text-[var(--color-ink-soft)]">
          Awaiting run.
        </p>
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
        <Loaded summary={state.result.summary} color={accent.color} wall={state.result.wall_time_ms} />
      )}
    </section>
  );
}
