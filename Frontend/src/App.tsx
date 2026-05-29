import { useEffect, useState } from "react";
import { fetchDatasets, runEvaluation } from "./api";
import ComparisonTable from "./components/ComparisonTable";
import DatasetPicker from "./components/DatasetPicker";
import HeadToHead from "./components/HeadToHead";
import ModelStatusBar from "./components/ModelStatusBar";
import SummaryCard from "./components/SummaryCards";
import TopBar from "./components/TopBar";
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
    // Fire both at once. Neither waits for the other, so each panel
    // finishes (or fails) on its own.
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
    <div className="mx-auto max-w-[1180px] px-6 sm:px-10">
      <TopBar />

      <main>
        {/* hero */}
        <section className="pt-10 sm:pt-16">
          <p className="tnum text-xs text-ink-faint">
            {new Date().toISOString().slice(0, 10)}
          </p>
          <h1 className="mt-3 font-display text-hero text-ink">Model comparison</h1>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-ink-soft">
            Two matching engines, one dataset — read side by side.
          </p>
        </section>

        {/* live model health */}
        <ModelStatusBar />

        {/* controls */}
        <div className="mt-10">
          <DatasetPicker
            datasets={datasets}
            value={dataset}
            onChange={setDataset}
            onRun={run}
            running={running}
          />
        </div>

        {/* head-to-head verdict, shown once both models have reported */}
        <HeadToHead
          ai={ai.status === "done" ? ai.result : null}
          rag={rag.status === "done" ? rag.result : null}
        />

        {/* per-model summaries, each with its own loading / error state */}
        <div className="mt-6 grid grid-cols-1 gap-6 md:grid-cols-2">
          <SummaryCard model="ai" state={ai} peer={rag} />
          <SummaryCard model="rag" state={rag} peer={ai} />
        </div>

        {/* per-scenario ledger */}
        {showTable && (
          <section className="mt-20">
            <div className="mb-5 flex items-baseline justify-between gap-3">
              <h2 className="font-display text-title text-ink">Per-match ledger</h2>
              <span className="text-xs text-ink-faint">joined by applicant</span>
            </div>
            <ComparisonTable ai={ai.result} rag={rag.result} />
          </section>
        )}

        <footer className="mt-20 mb-16 border-t border-line-soft pt-5 text-xs text-ink-faint">
          Scored against <span className="font-mono">ground_truth.json</span> · engines fall
          back to deterministic logic without a <span className="font-mono">GEMINI_API_KEY</span>.
        </footer>
      </main>
    </div>
  );
}
