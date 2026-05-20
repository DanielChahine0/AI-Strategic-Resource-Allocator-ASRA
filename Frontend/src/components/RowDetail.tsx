import { MODEL_LABELS } from "../api";
import { dec, int } from "../lib/format";
import type { EvalRow, ModelKey } from "../types";

const ACCENT: Record<ModelKey, string> = {
  ai: "var(--color-ai)",
  rag: "var(--color-rag)",
};

function Anchors({ row }: { row: EvalRow }) {
  const eq = row.explanation_quality;
  if (!eq) return null;
  const present = new Set(eq.anchors_present);
  return (
    <div className="flex flex-wrap gap-1.5">
      {eq.anchors_expected.map((a) => {
        const hit = present.has(a);
        return (
          <span
            key={a}
            className="tnum border px-1.5 py-0.5 text-[10px]"
            style={{
              borderColor: hit ? "var(--color-good)" : "var(--color-line)",
              color: hit ? "var(--color-good)" : "var(--color-ink-soft)",
              textDecoration: hit ? "none" : "line-through",
            }}
          >
            {a.replace(/^(usage|urgency):/, "")}
          </span>
        );
      })}
    </div>
  );
}

function Panel({ model, row }: { model: ModelKey; row?: EvalRow }) {
  const color = ACCENT[model];
  if (!row) {
    return (
      <div className="p-5 text-sm text-[var(--color-ink-soft)]">
        No result from {MODEL_LABELS[model]}.
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4 p-5" style={{ borderTop: `3px solid ${color}` }}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] uppercase tracking-[0.16em]" style={{ color }}>
          {MODEL_LABELS[model]}
        </span>
        {row.tier_recommendation_confidence !== null && (
          <span className="tnum text-[11px] text-[var(--color-ink-soft)]">
            tier pick confidence {dec(row.tier_recommendation_confidence)}
          </span>
        )}
      </div>

      {row.error ? (
        <p className="font-mono text-xs text-[var(--color-signal)]">{row.error}</p>
      ) : (
        <>
          <p className="text-sm leading-relaxed text-[var(--color-ink)]">
            {row.explanation || <span className="italic text-[var(--color-ink-soft)]">no explanation</span>}
          </p>

          <div>
            <p className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
              Words it used from the applicant
            </p>
            <Anchors row={row} />
          </div>

          {row.citations.length > 0 && (
            <div>
              <p className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-[var(--color-ink-soft)]">
                Sources it cited
              </p>
              <ul className="flex flex-col gap-1">
                {row.citations.map((c, i) => (
                  <li key={i} className="tnum text-[11px] text-[var(--color-ink)]">
                    • {c}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <dl className="grid grid-cols-3 gap-3 border-t border-[var(--color-line)] pt-3 text-[11px]">
            <div>
              <dt className="text-[var(--color-ink-soft)]">runner-up</dt>
              <dd className="tnum">{row.runner_up_device_id ?? "n/a"}</dd>
              <dd className="tnum text-[var(--color-ink-soft)]">{dec(row.runner_up_composite)}</dd>
            </div>
            <div>
              <dt className="text-[var(--color-ink-soft)]">tokens i/o</dt>
              <dd className="tnum">
                {int(row.tokens.input)}/{int(row.tokens.output)}
              </dd>
              <dd className="tnum text-[var(--color-ink-soft)]">{int(row.tokens.total)} total</dd>
            </div>
            <div>
              <dt className="text-[var(--color-ink-soft)]">expl. quality</dt>
              <dd className="tnum">{dec(row.explanation_quality?.score ?? null)}</dd>
              <dd className="tnum text-[var(--color-ink-soft)]">
                {row.explanation_quality?.cites_applicant_field ? "cites fields" : "generic"}
              </dd>
            </div>
          </dl>
        </>
      )}
    </div>
  );
}

export default function RowDetail({ ai, rag }: { ai?: EvalRow; rag?: EvalRow }) {
  return (
    <div className="grid grid-cols-1 divide-y divide-[var(--color-line)] bg-[var(--color-paper-2)]/40 md:grid-cols-2 md:divide-x md:divide-y-0">
      <Panel model="ai" row={ai} />
      <Panel model="rag" row={rag} />
    </div>
  );
}
