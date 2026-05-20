import { useState } from "react";
import { dec, SCENARIO_LABELS, sortScenarios } from "../lib/format";
import type { EvalResult, EvalRow, ModelKey } from "../types";
import RowDetail from "./RowDetail";

const ACCENT: Record<ModelKey, string> = {
  ai: "var(--color-ai)",
  rag: "var(--color-rag)",
};

interface Joined {
  scenario: string;
  ai?: EvalRow;
  rag?: EvalRow;
}

function join(ai: EvalResult | null, rag: EvalResult | null): Joined[] {
  const map = new Map<string, Joined>();
  const add = (r: EvalRow, key: ModelKey) => {
    const j = map.get(r.scenario) ?? { scenario: r.scenario };
    j[key] = r;
    map.set(r.scenario, j);
  };
  ai?.rows.forEach((r) => add(r, "ai"));
  rag?.rows.forEach((r) => add(r, "rag"));
  return sortScenarios([...map.keys()]).map((s) => map.get(s)!);
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
  if (ok === null || ok === undefined) return <span className="text-[var(--color-ink-soft)]">·</span>;
  return ok ? (
    <span style={{ color: "var(--color-good)" }}>✓</span>
  ) : (
    <span style={{ color: "var(--color-signal)" }}>✗</span>
  );
}

function Alloc({ row, model }: { row?: EvalRow; model: ModelKey }) {
  const color = ACCENT[model];
  if (!row) return <div className="px-4 py-3 text-xs text-[var(--color-ink-soft)]">—</div>;
  if (row.error)
    return <div className="px-4 py-3 font-mono text-[11px] text-[var(--color-signal)]">{row.error}</div>;
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-2">
        <span
          className="tnum px-1.5 py-0.5 text-[11px] font-semibold text-[var(--color-paper)]"
          style={{ backgroundColor: color }}
        >
          {row.chosen_category}/{row.chosen_tier ?? "—"}
        </span>
        <span className="tnum text-[11px] text-[var(--color-ink-soft)]">{row.chosen_device_id}</span>
      </div>
      <div className="flex items-center gap-3 text-[11px]">
        <span className="flex items-center gap-1" title="category / tier accuracy">
          <Mark ok={row.accuracy?.category_correct} />
          <Mark ok={row.accuracy?.tier_correct} />
        </span>
        <span className="tnum w-8 text-right text-[var(--color-ink-soft)]" title="composite">
          {dec(row.composite)}
        </span>
        <span className="tnum w-8 text-right" style={{ color }} title="confidence">
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
    <div className="rise border border-[var(--color-line)] bg-[var(--color-paper)]">
      {/* header */}
      <div className="grid grid-cols-[1.1fr_1.4fr_1.4fr] border-b border-[var(--color-ink)] bg-[var(--color-paper-2)]">
        <div className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.16em]">
          Scenario
        </div>
        <div
          className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.16em]"
          style={{ color: ACCENT.ai }}
        >
          AI Model
        </div>
        <div
          className="px-4 py-2.5 text-[11px] font-semibold uppercase tracking-[0.16em]"
          style={{ color: ACCENT.rag }}
        >
          RAG Model
        </div>
      </div>

      {rows.map((j, idx) => {
        const isOpen = open === j.scenario;
        const div = diverges(j.ai, j.rag);
        return (
          <div
            key={j.scenario}
            className="border-b border-[var(--color-line)] last:border-b-0"
            style={
              div
                ? {
                    boxShadow: "inset 3px 0 0 var(--color-signal)",
                    backgroundColor: "color-mix(in srgb, var(--color-signal) 4%, transparent)",
                  }
                : undefined
            }
          >
            <button
              onClick={() => setOpen(isOpen ? null : j.scenario)}
              aria-expanded={isOpen}
              className="group grid w-full grid-cols-[1.1fr_1.4fr_1.4fr] items-stretch text-left transition-colors hover:bg-[var(--color-paper-2)]"
              style={isOpen ? { backgroundColor: "var(--color-paper-2)" } : undefined}
            >
              <div className="flex items-center gap-2.5 px-4 py-3">
                <span className="tnum w-5 text-[10px] text-[var(--color-ink-soft)] transition-colors group-hover:text-[var(--color-ink)]">
                  {isOpen ? "▾" : String(idx + 1).padStart(2, "0")}
                </span>
                <div className="flex flex-col">
                  <span className="font-medium leading-tight">{j.scenario}</span>
                  <span className="text-[11px] text-[var(--color-ink-soft)]">
                    {SCENARIO_LABELS[j.scenario] ?? ""}
                  </span>
                </div>
                {div && (
                  <span className="ml-auto self-start border border-[var(--color-signal)] px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-[var(--color-signal)]">
                    diverges
                  </span>
                )}
              </div>
              <div className="border-l border-[var(--color-line)]">
                <Alloc row={j.ai} model="ai" />
              </div>
              <div className="border-l border-[var(--color-line)]">
                <Alloc row={j.rag} model="rag" />
              </div>
            </button>
            {isOpen && <RowDetail ai={j.ai} rag={j.rag} />}
          </div>
        );
      })}

      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-[var(--color-ink)] bg-[var(--color-paper-2)] px-4 py-2.5 text-[10px] text-[var(--color-ink-soft)]">
        <span>
          <Mark ok /> <Mark ok={false} /> = category · tier vs. ground truth
        </span>
        <span className="tnum">0.00 composite</span>
        <span className="tnum" style={{ color: ACCENT.ai }}>
          0.00 confidence
        </span>
        <span style={{ color: "var(--color-signal)" }}>▌ diverges = models chose differently</span>
        <span className="ml-auto italic">click a row to expand explanations</span>
      </div>
    </div>
  );
}
