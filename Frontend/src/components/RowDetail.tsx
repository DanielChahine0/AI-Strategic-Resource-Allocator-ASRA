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
  // Emphasis is inverted, not destructive: words the engine actually used are
  // solid ink; words it didn't are ghosted (no strikethrough — these are the
  // applicant's own natural-language phrases, set in sans, not mono).
  return (
    <div className="flex flex-wrap gap-2">
      {eq.anchors_expected.map((a) => {
        const hit = present.has(a);
        return (
          <span
            key={a}
            className={`rounded-md border px-2 py-0.5 text-[11px] leading-tight ${
              hit ? "border-line text-ink" : "border-line-soft text-ink-faint opacity-70"
            }`}
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
      <div className="p-6 text-sm text-ink-faint">No result from {MODEL_LABELS[model]}.</div>
    );
  }
  return (
    <div className="flex flex-col gap-4 p-6" style={{ borderTop: `2px solid ${color}` }}>
      <div className="flex items-center justify-between">
        <span
          className="font-mono text-[11px] uppercase tracking-[0.18em]"
          style={{ color }}
        >
          {MODEL_LABELS[model]}
        </span>
        {row.tier_recommendation_confidence !== null && (
          <span className="tnum text-[11px] text-ink-faint">
            tier confidence {dec(row.tier_recommendation_confidence)}
          </span>
        )}
      </div>

      {row.error ? (
        <p className="font-mono text-xs text-signal">{row.error}</p>
      ) : (
        <>
          <p className="text-sm leading-relaxed text-ink">
            {row.explanation || <span className="italic text-ink-faint">no explanation</span>}
          </p>

          <div>
            <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
              Words used from the applicant
            </p>
            <Anchors row={row} />
          </div>

          {row.citations.length > 0 && (
            <div>
              <p className="mb-2 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-faint">
                Sources cited
              </p>
              <ul className="flex flex-col gap-1">
                {row.citations.map((c, i) => (
                  <li key={i} className="tnum text-[11px] text-ink">
                    • {c}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <dl className="grid grid-cols-3 gap-3 border-t border-line pt-3.5 text-[11px]">
            <div>
              <dt className="text-ink-faint">runner-up</dt>
              <dd className="tnum text-ink">{row.runner_up_device_id ?? "n/a"}</dd>
              <dd className="tnum text-ink-faint">{dec(row.runner_up_composite)}</dd>
            </div>
            <div>
              <dt className="text-ink-faint">tokens i/o</dt>
              <dd className="tnum text-ink">
                {int(row.tokens.input)}/{int(row.tokens.output)}
              </dd>
              <dd className="tnum text-ink-faint">{int(row.tokens.total)} total</dd>
            </div>
            <div>
              <dt className="text-ink-faint">expl. quality</dt>
              <dd className="tnum text-ink">{dec(row.explanation_quality?.score ?? null)}</dd>
              <dd className="tnum text-ink-faint">
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
    <div className="grid grid-cols-1 divide-y divide-line bg-subtle/50 md:grid-cols-2 md:divide-x md:divide-y-0">
      <Panel model="ai" row={ai} />
      <Panel model="rag" row={rag} />
    </div>
  );
}
