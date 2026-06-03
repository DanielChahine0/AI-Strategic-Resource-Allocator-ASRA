import { useState } from "react";
import { MODEL_LABELS, runImpact } from "../api";
import { int, ms, pct } from "../lib/format";
import type { BatchItem, ImpactReport, ImpactRunState, ModelKey } from "../types";
import TokenLedger from "./TokenLedger";
import TopBar from "./TopBar";

const AREAS: { label: string; value: string | null }[] = [
  { label: "Etobicoke", value: "Etobicoke" },
  { label: "Scarborough", value: "Scarborough" },
  { label: "North York", value: "North York" },
  { label: "Downtown Toronto", value: "Downtown Toronto" },
  { label: "Mississauga", value: "Mississauga" },
  { label: "All areas", value: null },
];

const ACCENT: Record<ModelKey, string> = { ai: "var(--color-ai)", rag: "var(--color-rag)" };
const IDLE: ImpactRunState = { status: "idle", result: null, error: null };

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
        {label}
      </span>
      <span className="tnum text-metric leading-none text-ink">{value}</span>
      {hint && <span className="text-[11px] text-ink-faint">{hint}</span>}
    </div>
  );
}

function ApplicantRow({ item, accent }: { item: BatchItem; accent: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-line-soft last:border-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 py-2.5 text-left transition-colors hover:bg-subtle/50"
      >
        <span className="font-mono text-[12px] text-ink w-24 shrink-0">{item.applicant_id}</span>
        <span className="flex-1 truncate text-[12px] text-ink-soft">
          {item.matched_device_id ? (
            <>
              {item.matched_device_id}
              <span className="ml-1.5 font-mono text-[10px] text-ink-faint">
                {item.matched_tier}
              </span>
            </>
          ) : (
            <span className="text-signal">no match</span>
          )}
        </span>
        <span
          className="rounded px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.1em]"
          style={{ color: item.used_ai ? accent : undefined }}
        >
          {item.used_ai ? "AI" : "algo"}
        </span>
        <span className="tnum w-16 shrink-0 text-right text-[12px] text-ink">
          {int(item.tokens_total)}
        </span>
        <span className="w-4 shrink-0 text-center text-[11px] text-ink-faint">
          {open ? "−" : "+"}
        </span>
      </button>
      {open && (
        <div className="px-2 pb-4">
          {item.explanation && (
            <p className="mb-3 text-[12px] leading-relaxed text-ink-soft">{item.explanation}</p>
          )}
          <TokenLedger steps={item.token_steps} />
        </div>
      )}
    </div>
  );
}

function ModelPanel({ model, state }: { model: ModelKey; state: ImpactRunState }) {
  const accent = ACCENT[model];
  return (
    <section className="card rounded-card border border-line bg-surface p-7">
      <header className="mb-5 flex items-center gap-3">
        <span className="h-2 w-2 rounded-full" style={{ backgroundColor: accent }} aria-hidden />
        <h2 className="font-display text-title leading-none text-ink">{MODEL_LABELS[model]}</h2>
      </header>

      {state.status === "idle" && (
        <p className="py-10 text-center font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">
          Awaiting run
        </p>
      )}
      {state.status === "loading" && (
        <div className="flex flex-col gap-3 py-6" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="sweep h-6 rounded-lg bg-subtle" />
          ))}
        </div>
      )}
      {state.status === "error" && (
        <div className="rounded-xl border border-signal/40 bg-signal-soft/60 p-4">
          <p className="font-mono text-xs leading-relaxed text-ink">{state.error}</p>
        </div>
      )}
      {state.status === "done" && state.result && (
        <Loaded report={state.result} accent={accent} />
      )}
    </section>
  );
}

function Loaded({ report, accent }: { report: ImpactReport; accent: string }) {
  return (
    <div className="flex flex-col gap-7">
      <div className="grid grid-cols-2 gap-x-8 gap-y-5 sm:grid-cols-3">
        <Stat
          label="Matched"
          value={`${report.matched}/${report.applicants}`}
          hint={`${pct(report.match_rate)} of applicants`}
        />
        <Stat
          label="Tokens"
          value={int(report.tokens_total)}
          hint={`avg ${int(Math.round(report.avg_tokens_per_applicant))}/applicant`}
        />
        <Stat
          label="AI calls"
          value={`${report.resolved_with_ai}`}
          hint={`${report.resolved_deterministically} resolved by algorithm`}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
          matched by tier
        </span>
        <div className="flex flex-wrap gap-2">
          {Object.entries(report.by_matched_tier).map(([tier, n]) => (
            <span
              key={tier}
              className="tnum rounded-full bg-subtle px-2.5 py-1 text-[11px] text-ink-soft"
            >
              {tier}: {n}
            </span>
          ))}
          {report.unmatched > 0 && (
            <span className="tnum rounded-full bg-signal-soft px-2.5 py-1 text-[11px] text-signal">
              unmatched: {report.unmatched}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <div className="mb-1 flex items-center justify-between">
          <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-faint">
            applicants — click to see token steps
          </span>
          <span className="text-[11px] text-ink-faint">{ms(report.wall_time_ms)}</span>
        </div>
        {report.batch.items.map((it) => (
          <ApplicantRow key={it.applicant_id} item={it} accent={accent} />
        ))}
      </div>
    </div>
  );
}

export default function Impact() {
  const [area, setArea] = useState<string | null>("Etobicoke");
  const [ai, setAi] = useState<ImpactRunState>(IDLE);
  const [rag, setRag] = useState<ImpactRunState>(IDLE);
  const running = ai.status === "loading" || rag.status === "loading";

  function run(force = false) {
    const dispatch = (
      model: ModelKey,
      set: React.Dispatch<React.SetStateAction<ImpactRunState>>,
    ) => {
      set({ status: "loading", result: null, error: null });
      runImpact(model, area, force)
        .then((result) => set({ status: "done", result, error: null }))
        .catch((e: Error) => set({ status: "error", result: null, error: e.message }));
    };
    dispatch("ai", setAi);
    dispatch("rag", setRag);
  }

  // Token delta between the two models once both are in.
  const aiTok = ai.result?.tokens_total ?? null;
  const ragTok = rag.result?.tokens_total ?? null;

  return (
    <div className="mx-auto max-w-[1180px] px-6 sm:px-10">
      <TopBar />
      <main>
        <section className="pt-10 sm:pt-16">
          <p className="tnum text-xs text-ink-faint">{new Date().toISOString().slice(0, 10)}</p>
          <h1 className="mt-3 font-display text-hero text-ink">Community impact</h1>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-ink-soft">
            Run a neighbourhood's applicants through both engines against the live refurbished
            inventory — and see exactly where every token is spent.
          </p>
        </section>

        <div className="mt-10 flex flex-wrap items-center gap-2">
          {AREAS.map((a) => {
            const active = area === a.value;
            return (
              <button
                key={a.label}
                type="button"
                onClick={() => setArea(a.value)}
                aria-pressed={active}
                className={`min-h-9 rounded-full px-3.5 text-[13px] transition-colors ${
                  active ? "bg-ink text-canvas" : "text-ink-soft hover:text-ink"
                }`}
              >
                {a.label}
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => run(false)}
            disabled={running}
            className="ml-auto min-h-9 rounded-full bg-ink px-5 text-[13px] text-canvas transition-opacity disabled:opacity-50"
          >
            {running ? "Running…" : "Run impact"}
          </button>
          {(ai.status === "done" || rag.status === "done") && (
            <button
              type="button"
              onClick={() => run(true)}
              disabled={running}
              className="min-h-9 rounded-full px-3.5 text-[13px] text-ink-soft hover:text-ink disabled:opacity-50"
              title="Bypass cache and re-run (spends tokens)"
            >
              Run again
            </button>
          )}
        </div>

        {aiTok !== null && ragTok !== null && (
          <p className="mt-6 text-[13px] text-ink-soft">
            For{" "}
            <span className="text-ink">{area ?? "all areas"}</span>: AI model spent{" "}
            <span className="tnum text-ink">{int(aiTok)}</span> tokens, RAG spent{" "}
            <span className="tnum text-ink">{int(ragTok)}</span>{" "}
            <span className="text-ink-faint">
              ({aiTok <= ragTok ? "AI" : "RAG"} cheaper by {int(Math.abs(aiTok - ragTok))})
            </span>
            .
          </p>
        )}

        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
          <ModelPanel model="ai" state={ai} />
          <ModelPanel model="rag" state={rag} />
        </div>

        <footer className="mt-20 mb-16 border-t border-line-soft pt-5 text-xs text-ink-faint">
          First-come-first-serve over <span className="font-mono">sample_simple/applicants.json</span>{" "}
          · Q1 (OS) and software checks are deterministic (0 tokens); only the one fit+explain call
          spends tokens.
        </footer>
      </main>
    </div>
  );
}
