import { useState } from "react";
import { dec, SCENARIO_LABELS, SCENARIO_ORDER } from "../lib/format";
import type { EvalResult, EvalRow, ModelKey } from "../types";
import RowDetail from "./RowDetail";

const ACCENT: Record<ModelKey, { color: string; soft: string }> = {
  ai: { color: "var(--color-ai)", soft: "var(--color-ai-soft)" },
  rag: { color: "var(--color-rag)", soft: "var(--color-rag-soft)" },
};

interface Joined {
  applicant_id: string;
  scenario: string;
  ai?: EvalRow;
  rag?: EvalRow;
}

// Join the two models' rows on `applicant_id` — the stable per-applicant
// identity. Keying on `scenario` (as this once did) silently collapses two
// distinct applicants into one row if they ever share a scenario string, and
// drops the loser's result. The scenario is kept only as a display label.
function join(ai: EvalResult | null, rag: EvalResult | null): Joined[] {
  const map = new Map<string, Joined>();
  const add = (r: EvalRow, key: ModelKey) => {
    const j = map.get(r.applicant_id) ?? {
      applicant_id: r.applicant_id,
      scenario: r.scenario,
    };
    j[key] = r;
    map.set(r.applicant_id, j);
  };
  ai?.rows.forEach((r) => add(r, "ai"));
  rag?.rows.forEach((r) => add(r, "rag"));
  return [...map.values()].sort((a, b) => {
    const ia = SCENARIO_ORDER.indexOf(a.scenario);
    const ib = SCENARIO_ORDER.indexOf(b.scenario);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib) || a.applicant_id.localeCompare(b.applicant_id);
  });
}

function diverges(a?: EvalRow, b?: EvalRow): boolean {
  if (!a || !b) return false;
  return (
    a.chosen_category !== b.chosen_category ||
    a.chosen_tier !== b.chosen_tier ||
    a.chosen_device_id !== b.chosen_device_id
  );
}

function Mark({ ok }: { ok: boolean | null | undefined }) {
  if (ok === null || ok === undefined) return <span className="text-ink-faint">·</span>;
  return ok ? (
    <span className="text-ink">✓</span>
  ) : (
    <span style={{ color: "var(--color-signal)" }}>✗</span>
  );
}

function Alloc({ row, model }: { row?: EvalRow; model: ModelKey }) {
  const accent = ACCENT[model];
  if (!row) return <div className="px-4 py-3.5 text-xs text-ink-faint">no result</div>;
  if (row.error)
    return <div className="px-4 py-3.5 font-mono text-[11px] text-signal">{row.error}</div>;
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3.5">
      <div className="flex items-center gap-2.5">
        <span
          className="tnum rounded-md px-1.5 py-0.5 text-[11px] font-medium"
          style={{ backgroundColor: accent.soft, color: accent.color }}
        >
          {row.chosen_category}/{row.chosen_tier ?? "n/a"}
        </span>
        <span className="tnum text-[11px] text-ink-faint">{row.chosen_device_id}</span>
      </div>
      <div className="flex items-center gap-3 text-[11px]">
        <span className="flex items-center gap-1" title="category / tier accuracy">
          <Mark ok={row.accuracy?.category_correct} />
          <Mark ok={row.accuracy?.tier_correct} />
        </span>
        <span className="tnum w-8 text-right text-ink-faint" title="composite">
          {dec(row.composite)}
        </span>
        <span className="tnum w-8 text-right" style={{ color: accent.color }} title="confidence">
          {dec(row.confidence)}
        </span>
      </div>
    </div>
  );
}

export default function ComparisonTable({
  ai,
  rag,
}: {
  ai: EvalResult | null;
  rag: EvalResult | null;
}) {
  const rows = join(ai, rag);
  const [open, setOpen] = useState<string | null>(null);
  if (rows.length === 0) return null;

  return (
    <div className="card rise overflow-hidden rounded-card border border-line bg-surface">
      {/* header */}
      <div className="grid grid-cols-[1.1fr_1.4fr_1.4fr] border-b border-line bg-subtle">
        <div className="px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-ink-soft">
          Scenario
        </div>
        <div
          className="px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-[0.18em]"
          style={{ color: ACCENT.ai.color }}
        >
          AI Model
        </div>
        <div
          className="px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-[0.18em]"
          style={{ color: ACCENT.rag.color }}
        >
          RAG Model
        </div>
      </div>

      {rows.map((j, idx) => {
        const isOpen = open === j.applicant_id;
        const div = diverges(j.ai, j.rag);
        return (
          <div
            key={j.applicant_id}
            className="border-b border-line-soft last:border-b-0"
            style={
              div
                ? {
                    boxShadow: "inset 2px 0 0 var(--color-signal)",
                    backgroundColor: "color-mix(in srgb, var(--color-signal) 3%, transparent)",
                  }
                : undefined
            }
          >
            <button
              onClick={() => setOpen(isOpen ? null : j.applicant_id)}
              aria-expanded={isOpen}
              className="group grid w-full grid-cols-[1.1fr_1.4fr_1.4fr] items-stretch text-left transition-colors hover:bg-subtle"
              style={isOpen ? { backgroundColor: "var(--color-subtle)" } : undefined}
            >
              <div className="flex items-center gap-2.5 px-4 py-3.5">
                <span className="tnum w-5 text-[10px] text-ink-faint transition-colors group-hover:text-ink">
                  {isOpen ? "▾" : String(idx + 1).padStart(2, "0")}
                </span>
                <div className="flex flex-col">
                  <span className="font-medium leading-tight text-ink">{j.scenario}</span>
                  <span className="text-[11px] text-ink-faint">
                    {SCENARIO_LABELS[j.scenario] ?? ""}
                  </span>
                </div>
                {div && (
                  <span className="ml-auto self-start rounded-md border border-signal/50 px-1.5 py-0.5 font-mono text-[9px] font-medium uppercase tracking-[0.1em] text-signal">
                    diverges
                  </span>
                )}
              </div>
              <div className="border-l border-line-soft">
                <Alloc row={j.ai} model="ai" />
              </div>
              <div className="border-l border-line-soft">
                <Alloc row={j.rag} model="rag" />
              </div>
            </button>
            {isOpen && <RowDetail ai={j.ai} rag={j.rag} />}
          </div>
        );
      })}

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line bg-subtle px-4 py-3 text-[10px] text-ink-faint">
        <span>
          <Mark ok /> <Mark ok={false} /> category · tier vs answer key
        </span>
        <span className="tnum">0.00 composite</span>
        <span className="tnum">0.00 confidence (per engine)</span>
      </div>
    </div>
  );
}
