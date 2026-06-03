import { useEffect, useState } from "react";
import { fetchInventory, MODEL_LABELS } from "../api";
import { int } from "../lib/format";
import type { DatasetDevice, InventoryResponse, ModelKey } from "../types";
import TopBar from "./TopBar";

type State = { status: "idle" | "loading" | "done" | "error"; data: InventoryResponse | null; error: string | null };
const IDLE: State = { status: "idle", data: null, error: null };

const TIER_LABEL: Record<string, string> = { T1: "High power", T2: "Standard", T3: "Basic" };

export default function InventoryView() {
  const [model, setModel] = useState<ModelKey>("ai");
  const [state, setState] = useState<State>(IDLE);

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading", data: null, error: null });
    fetchInventory(model)
      .then((data) => !cancelled && setState({ status: "done", data, error: null }))
      .catch((e: Error) => !cancelled && setState({ status: "error", data: null, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [model]);

  function refresh() {
    setState({ status: "loading", data: null, error: null });
    fetchInventory(model, true)
      .then((data) => setState({ status: "done", data, error: null }))
      .catch((e: Error) => setState({ status: "error", data: null, error: e.message }));
  }

  const counts = state.data?.counts;
  return (
    <div className="mx-auto max-w-[1180px] px-6 sm:px-10">
      <TopBar />
      <main>
        <section className="pt-10 sm:pt-16">
          <p className="tnum text-xs text-ink-faint">{new Date().toISOString().slice(0, 10)}</p>
          <h1 className="mt-3 font-display text-hero text-ink">Refurbished inventory</h1>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-ink-soft">
            Live from the LGT donation sheet — only computers marked{" "}
            <span className="font-mono text-[13px]">Refurbished&nbsp;ready&nbsp;for&nbsp;distribution</span>.
          </p>
        </section>

        <div className="mt-8 flex items-center gap-2">
          {(["ai", "rag"] as ModelKey[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setModel(m)}
              aria-pressed={model === m}
              className={`min-h-9 rounded-full px-3.5 text-[13px] transition-colors ${
                model === m ? "bg-ink text-canvas" : "text-ink-soft hover:text-ink"
              }`}
            >
              {MODEL_LABELS[m]}
            </button>
          ))}
          <button
            type="button"
            onClick={refresh}
            className="ml-auto min-h-9 rounded-full px-3.5 text-[13px] text-ink-soft hover:text-ink"
            title="Bypass cache and re-pull the sheet"
          >
            Refresh
          </button>
        </div>

        {counts && (
          <p className="mt-5 text-[13px] text-ink-soft">
            <span className="tnum text-ink">{int(counts.machines ?? 0)}</span> allocatable computers
            {" "}from <span className="tnum text-ink">{int(counts.refurbished ?? 0)}</span> refurbished-ready
            rows <span className="text-ink-faint">(source: {String(counts.source ?? "?")})</span>.
          </p>
        )}

        {state.status === "loading" && (
          <div className="mt-8 flex flex-col gap-3" aria-busy="true">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="sweep h-10 rounded-lg bg-subtle" />
            ))}
          </div>
        )}
        {state.status === "error" && (
          <div className="mt-8 rounded-xl border border-signal/40 bg-signal-soft/60 p-4">
            <p className="font-mono text-xs leading-relaxed text-ink">{state.error}</p>
          </div>
        )}

        {state.status === "done" && state.data && (
          <div className="mt-8 overflow-hidden rounded-card border border-line bg-surface">
            <table className="w-full text-left text-[13px]">
              <thead>
                <tr className="border-b border-line text-ink-faint">
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.14em]">ID</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.14em]">Tier</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.14em]">CPU</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.14em]">RAM</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-[0.14em]">Cond.</th>
                </tr>
              </thead>
              <tbody>
                {state.data.devices.map((d: DatasetDevice) => (
                  <tr key={d.id} className="border-b border-line-soft last:border-0">
                    <td className="px-4 py-2.5 font-mono text-[12px] text-ink">{d.id}</td>
                    <td className="px-4 py-2.5 text-ink-soft">
                      {d.tier}
                      {d.tier && TIER_LABEL[d.tier] && (
                        <span className="ml-1.5 text-[11px] text-ink-faint">{TIER_LABEL[d.tier]}</span>
                      )}
                    </td>
                    <td className="px-4 py-2.5 text-ink-soft">{d.specs.cpu ?? "—"}</td>
                    <td className="tnum px-4 py-2.5 text-ink-soft">
                      {d.specs.ram_gb ? `${d.specs.ram_gb} GB` : "—"}
                    </td>
                    <td className="tnum px-4 py-2.5 text-ink-soft">{d.condition}/5</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <footer className="mt-20 mb-16 border-t border-line-soft pt-5 text-xs text-ink-faint">
          Tier is derived from CPU/RAM · cached 60s client-side, 5&nbsp;min server-side.
        </footer>
      </main>
    </div>
  );
}
