import { MODEL_LABELS } from "../api";
import { int, ms, pct } from "../lib/format";
import type { EvalResult, EvalSummary, ModelKey } from "../types";

const AI = "var(--color-ai)";
const RAG = "var(--color-rag)";

/** Which model wins, given that higher (or lower) is better. */
function leader(a: number, b: number, lowerIsBetter = false): ModelKey | null {
  if (a === b) return null;
  const aWins = lowerIsBetter ? a < b : a > b;
  return aWins ? "ai" : "rag";
}

function LeadPill({ winner, delta }: { winner: ModelKey | null; delta: string }) {
  if (!winner)
    return (
      <span className="text-[10px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
        tie
      </span>
    );
  const color = winner === "ai" ? AI : RAG;
  return (
    <span
      className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.12em]"
      style={{ color }}
    >
      <span aria-hidden>▲</span>
      {MODEL_LABELS[winner].replace(" Model", "")} {delta}
    </span>
  );
}

/** A quality metric (0..1, higher is better): paired bars on a shared scale. */
function QualityBar({
  label,
  ai,
  rag,
}: {
  label: string;
  ai: number;
  rag: number;
}) {
  const winner = leader(ai, rag);
  const delta = `+${pct(Math.abs(ai - rag))}`;
  const Row = ({ model, value }: { model: ModelKey; value: number }) => {
    const color = model === "ai" ? AI : RAG;
    return (
      <div className="flex items-center gap-2.5">
        <span className="w-7 text-[10px] uppercase tracking-[0.1em] text-[var(--color-ink-soft)]">
          {model}
        </span>
        <div className="relative h-2 flex-1 bg-[var(--color-paper-2)]">
          <div
            className="grow absolute inset-y-0 left-0"
            style={{ width: `${Math.max(1, value * 100)}%`, backgroundColor: color }}
          />
        </div>
        <span className="tnum w-10 text-right text-xs font-semibold">{pct(value)}</span>
      </div>
    );
  };
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
          {label}
        </span>
        <LeadPill winner={winner} delta={delta} />
      </div>
      <Row model="ai" value={ai} />
      <Row model="rag" value={rag} />
    </div>
  );
}

/** A cost metric (lower is better): two numbers + who wins by how much. */
function CostStat({
  label,
  aiValue,
  ragValue,
  format,
  verb,
}: {
  label: string;
  aiValue: number;
  ragValue: number;
  format: (v: number) => string;
  verb: string;
}) {
  const bothZero = aiValue === 0 && ragValue === 0;
  const winner = bothZero ? null : leader(aiValue, ragValue, true);
  const hi = Math.max(aiValue, ragValue);
  const lo = Math.min(aiValue, ragValue);
  const saving = hi > 0 ? Math.round(((hi - lo) / hi) * 100) : 0;
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
        {label}
      </span>
      <div className="flex items-baseline gap-3">
        <span className="tnum text-base font-semibold" style={{ color: AI }}>
          {format(aiValue)}
        </span>
        <span className="text-[var(--color-line)]">·</span>
        <span className="tnum text-base font-semibold" style={{ color: RAG }}>
          {format(ragValue)}
        </span>
      </div>
      {winner ? (
        <span
          className="text-[10px] uppercase tracking-[0.12em]"
          style={{ color: winner === "ai" ? AI : RAG }}
        >
          {MODEL_LABELS[winner].replace(" Model", "")} {verb} {saving}% less
        </span>
      ) : (
        <span className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-ink-soft)]">
          {bothZero ? "no live tokens" : "even"}
        </span>
      )}
    </div>
  );
}

export default function HeadToHead({
  ai,
  rag,
}: {
  ai: EvalResult | null;
  rag: EvalResult | null;
}) {
  // The head-to-head only makes sense once both engines have reported.
  if (!ai || !rag) return null;
  const a: EvalSummary = ai.summary;
  const r: EvalSummary = rag.summary;

  return (
    <section className="card rise mt-8 border border-[var(--color-line)] bg-[var(--color-paper)] p-6 sm:p-7">
      <header className="mb-5 flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--color-line)] pb-3">
        <h2 className="font-[family-name:var(--font-display)] text-xl font-semibold">
          Head to head
        </h2>
        <div className="flex items-center gap-4 text-[10px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2" style={{ backgroundColor: AI }} /> AI
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2" style={{ backgroundColor: RAG }} /> RAG
          </span>
          <span className="hidden sm:inline">same 0 to 100% scale</span>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-x-10 gap-y-5 md:grid-cols-3">
        <QualityBar label="Accuracy" ai={a.mean_accuracy_score} rag={r.mean_accuracy_score} />
        <QualityBar label="Confidence" ai={a.mean_confidence} rag={r.mean_confidence} />
        <QualityBar
          label="Explanation quality"
          ai={a.mean_explanation_quality}
          rag={r.mean_explanation_quality}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-x-10 gap-y-4 border-t border-[var(--color-line)] pt-5 sm:grid-cols-3">
        <CostStat
          label="Tokens (total)"
          aiValue={a.tokens_total}
          ragValue={r.tokens_total}
          format={int}
          verb="spends"
        />
        <CostStat
          label="Wall time"
          aiValue={ai.wall_time_ms}
          ragValue={rag.wall_time_ms}
          format={ms}
          verb="finishes in"
        />
        <CostStat
          label="Fallback rate"
          aiValue={a.fallback_rate}
          ragValue={r.fallback_rate}
          format={pct}
          verb="falls back"
        />
      </div>
    </section>
  );
}
