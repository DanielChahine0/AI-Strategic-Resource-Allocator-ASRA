import { int } from "../lib/format";
import type { TokenStep, TokenStepKind } from "../types";

// One muted style per step kind. Deterministic steps read as quiet/zero; the
// single AI call is the only row that carries real spend, in the model accent.
const KIND_STYLE: Record<TokenStepKind, string> = {
  algorithm: "bg-subtle text-ink-faint",
  ai: "bg-good-soft text-good",
  cache: "bg-good-soft text-good",
  fallback: "bg-signal-soft text-signal",
};

const KIND_LABEL: Record<TokenStepKind, string> = {
  algorithm: "algorithm",
  ai: "AI call",
  cache: "cached",
  fallback: "fallback",
};

/**
 * Per-step token ledger for one allocation: each pipeline step, whether it was
 * pure algorithm (0 tokens) or the lone LLM call, and the running cumulative
 * total. Makes "the AI is used only where it must be" literally visible.
 */
export default function TokenLedger({ steps }: { steps: TokenStep[] }) {
  if (!steps?.length) {
    return <p className="font-mono text-[11px] text-ink-faint">no token steps recorded</p>;
  }
  const total = steps[steps.length - 1]?.cumulative_total ?? 0;
  return (
    <div className="flex flex-col gap-1.5">
      {steps.map((s) => {
        const zero = s.total_tokens === 0;
        return (
          <div
            key={s.step}
            className="flex items-center gap-3 border-b border-line-soft pb-1.5 last:border-0"
          >
            <span className="font-mono text-[11px] text-ink-soft w-28 shrink-0">{s.step}</span>
            <span
              className={`rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em] ${KIND_STYLE[s.kind]}`}
            >
              {KIND_LABEL[s.kind]}
            </span>
            <span className="flex-1 truncate text-[11px] text-ink-faint" title={s.detail}>
              {s.detail}
            </span>
            <span className={`tnum text-[12px] ${zero ? "text-ink-faint" : "text-ink"}`}>
              {zero ? "0" : `+${int(s.total_tokens)}`}
            </span>
            <span className="tnum w-14 shrink-0 text-right text-[11px] text-ink-faint">
              {int(s.cumulative_total)}
            </span>
          </div>
        );
      })}
      <div className="mt-1 flex items-center justify-between">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
          total
        </span>
        <span className="tnum text-[13px] text-ink">{int(total)} tokens</span>
      </div>
    </div>
  );
}
