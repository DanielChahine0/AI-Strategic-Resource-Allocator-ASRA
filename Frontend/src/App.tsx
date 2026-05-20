import { useEffect, useState } from "react";
import { fetchDatasets, runEvaluation } from "./api";
import ComparisonTable from "./components/ComparisonTable";
import DatasetPicker from "./components/DatasetPicker";
import HeadToHead from "./components/HeadToHead";
import ModelStatusBar from "./components/ModelStatusBar";
import SummaryCard from "./components/SummaryCards";
import type { ModelKey, ModelRunState } from "./types";

const IDLE: ModelRunState = { status: "idle", result: null, error: null };

export default function ModelComparison() {
  const [datasets, setDatasets] = useState<string[]>([]);
  const [dataset, setDataset] = useState<string>("");
  const [ai, setAi] = useState<ModelRunState>(IDLE);
  const [rag, setRag] = useState<ModelRunState>(IDLE);

  // Pull the dataset list from whichever backend answers first.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      for (const m of ["ai", "rag"] as ModelKey[]) {
        try {
          const ds = await fetchDatasets(m);
          if (!cancelled && ds.length) {
            setDatasets(ds);
            setDataset((cur) => cur || ds[0]);
            return;
          }
        } catch {
          /* try the other model */
        }
      }
      if (!cancelled) setDataset((cur) => cur || "sample-v1");
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const running = ai.status === "loading" || rag.status === "loading";

  function run() {
    if (!dataset) return;
    // Fire both independently — neither awaits the other, so each panel
    // resolves (or fails) on its own schedule.
    const dispatch = (
      model: ModelKey,
      set: React.Dispatch<React.SetStateAction<ModelRunState>>,
    ) => {
      set({ status: "loading", result: null, error: null });
      runEvaluation(model, dataset)
        .then((result) => set({ status: "done", result, error: null }))
        .catch((e: Error) => set({ status: "error", result: null, error: e.message }));
    };
    dispatch("ai", setAi);
    dispatch("rag", setRag);
  }

  const showTable = ai.status === "done" || rag.status === "done";

  return (
    <div className="relative z-10 mx-auto max-w-6xl px-6 py-10 sm:px-10 sm:py-14">
      {/* masthead */}
      <header className="border-b-2 border-[var(--color-ink)] pb-6">
        <div className="flex items-baseline justify-between">
          <span className="text-[11px] uppercase tracking-[0.3em] text-[var(--color-ink-soft)]">
            ASRA · Allocation Bench
          </span>
          <span className="tnum text-[11px] text-[var(--color-ink-soft)]">
            {new Date().toISOString().slice(0, 10)}
          </span>
        </div>
        <h1 className="mt-3 font-[family-name:var(--font-display)] text-5xl font-semibold leading-[0.95] tracking-tight sm:text-6xl">
          Model Comparison
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[var(--color-ink-soft)]">
          Run the deterministic <em>AI Model</em> and the retrieval-augmented{" "}
          <em>RAG Model</em> over the same labelled dataset and read them side by side —
          token cost, accuracy against the LGT precedent, confidence, and how well each
          rationale cites the applicant's own words.
        </p>
      </header>

      {/* live model health */}
      <ModelStatusBar />

      {/* controls */}
      <div className="pt-8">
        <DatasetPicker
          datasets={datasets}
          value={dataset}
          onChange={setDataset}
          onRun={run}
          running={running}
        />
      </div>

      {/* head-to-head verdict — appears once both engines have reported */}
      <HeadToHead
        ai={ai.status === "done" ? ai.result : null}
        rag={rag.status === "done" ? rag.result : null}
      />

      {/* summaries — independent loading/error per model */}
      <div className="mt-8 grid grid-cols-1 gap-5 md:grid-cols-2">
        <SummaryCard model="ai" state={ai} peer={rag} />
        <SummaryCard model="rag" state={rag} peer={ai} />
      </div>

      {/* per-scenario ledger */}
      {showTable && (
        <div className="mt-10">
          <h2 className="mb-4 flex items-baseline gap-3 font-[family-name:var(--font-display)] text-2xl font-semibold">
            Per-match ledger
            <span className="text-[11px] font-normal uppercase tracking-[0.16em] text-[var(--color-ink-soft)]">
              joined by scenario
            </span>
          </h2>
          <ComparisonTable ai={ai.result} rag={rag.result} />
        </div>
      )}

      <footer className="mt-14 border-t border-[var(--color-line)] pt-4 text-[11px] text-[var(--color-ink-soft)]">
        Accuracy is measured against{" "}
        <span className="font-mono">sample_data/ground_truth.json</span> (derived from the LGT
        precedent decisions, pending human validation). Token counts are live only when each
        backend has a <span className="font-mono">GEMINI_API_KEY</span>; otherwise the engines run
        deterministic fallbacks (0 tokens).
      </footer>
    </div>
  );
}
