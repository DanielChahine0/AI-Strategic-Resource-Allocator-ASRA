import { useEffect, useMemo, useState } from "react";
import { fetchDataset, fetchDatasets, MODEL_LABELS } from "../api";
import type {
  CurrentTechAccessObj,
  DatasetApplicant,
  DatasetDevice,
  DatasetIntake,
  DatasetPayload,
  GroundTruthLabel,
  ModelKey,
} from "../types";
import { SCENARIO_LABELS, sortScenarios } from "../lib/format";
import TopBar from "./TopBar";

type Tab = "applicants" | "inventory" | "ground";

const MODEL_ACCENT: Record<ModelKey, string> = {
  ai: "var(--color-ai)",
  rag: "var(--color-rag)",
};

const TIER: Record<string, { label: string; tone: string }> = {
  T1: { label: "T1 · High power", tone: "var(--color-ai)" },
  T2: { label: "T2 · Standard", tone: "var(--color-rag)" },
  T3: { label: "T3 · Basic", tone: "var(--color-ink-faint)" },
};

// Neutral ink ramp + signal for critical. The dataset is the shared input both
// engines score against, so urgency must NOT borrow a model accent (clay/teal).
const URGENCY_TONE: Record<string, string> = {
  critical: "var(--color-signal)",
  high: "var(--color-ink)",
  medium: "var(--color-ink-soft)",
  low: "var(--color-ink-faint)",
};

const ITEM_TYPE_ORDER = ["computer", "mobile", "display", "input"];

// --- normalizers: the two backends disagree on the applicant intake shape ---

const applicantId = (a: DatasetApplicant): string => a.id ?? a.applicant_id ?? "n/a";

const usageText = (u: DatasetIntake["main_usage"]): string =>
  Array.isArray(u) ? u.join(" · ") : (u ?? "");

function techAccessLine(t: DatasetIntake["current_tech_access"]): string {
  if (!t) return "n/a";
  if (typeof t === "string") return t.replace(/_/g, " ");
  const parts: string[] = [];
  if (t.device_situation) parts.push(t.device_situation.replace(/_/g, " "));
  if (t.has_internet != null) parts.push(t.has_internet ? "has internet" : "no internet");
  return parts.join(" · ") || "n/a";
}

function techNotes(t: DatasetIntake["current_tech_access"]): string | null {
  return t && typeof t === "object" ? ((t as CurrentTechAccessObj).notes ?? null) : null;
}

// --- small presentational atoms -------------------------------------------

function Chip({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return (
    <span
      className="inline-flex items-center rounded-md border px-2 py-0.5 font-mono text-[11px] leading-tight"
      style={{
        borderColor: tone ? `color-mix(in srgb, ${tone} 35%, transparent)` : "var(--color-line)",
        color: tone ?? "var(--color-ink-soft)",
      }}
    >
      {children}
    </span>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono text-[10px] font-medium uppercase tracking-[0.18em] text-ink-faint">
      {children}
    </span>
  );
}

function Condition({ value }: { value: number }) {
  return (
    <span className="tnum tracking-tight text-ink" title={`Condition ${value}/5`}>
      {"●".repeat(value)}
      <span className="text-line">{"○".repeat(Math.max(0, 5 - value))}</span>
    </span>
  );
}

// --- applicants ------------------------------------------------------------

function ApplicantCard({
  applicant,
  truth,
}: {
  applicant: DatasetApplicant;
  truth?: GroundTruthLabel;
}) {
  const intake = applicant.intake;
  const id = applicantId(applicant);
  const urgency = (intake.urgency ?? "").toLowerCase();
  const notes = techNotes(intake.current_tech_access);
  return (
    <article className="card card-lift rise flex flex-col gap-3.5 rounded-card border border-line bg-surface p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="tnum text-[11px] text-ink-faint">{id}</span>
          <h3 className="font-display text-xl leading-tight text-ink">{intake.who_needs_it}</h3>
        </div>
        {urgency && (
          <span
            className="shrink-0 rounded-full px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-canvas"
            style={{ backgroundColor: URGENCY_TONE[urgency] ?? "var(--color-ink-faint)" }}
          >
            {urgency}
          </span>
        )}
      </header>

      <div className="flex flex-wrap gap-1.5">
        {intake.purpose?.map((p) => (
          <Chip key={p} tone="var(--color-ink)">
            {SCENARIO_LABELS[p] ?? p}
          </Chip>
        ))}
        {intake.a3_subtrack && <Chip>{intake.a3_subtrack.replace(/_/g, " ")}</Chip>}
      </div>

      <div className="flex flex-col gap-1">
        <FieldLabel>Main usage</FieldLabel>
        <p className="text-sm leading-relaxed text-ink">{usageText(intake.main_usage)}</p>
      </div>

      {intake.software_needed?.length > 0 && (
        <div className="flex flex-col gap-2">
          <FieldLabel>Software</FieldLabel>
          <div className="flex flex-wrap gap-1.5">
            {intake.software_needed.map((s) => (
              <Chip key={s}>{s}</Chip>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <FieldLabel>Current access</FieldLabel>
        <p className="text-sm text-ink">
          {techAccessLine(intake.current_tech_access)}
          <span className="text-ink-faint">
            {" "}
            · {intake.shared_user_count} {intake.shared_user_count === 1 ? "user" : "users"}
          </span>
        </p>
        {notes && <p className="text-xs italic text-ink-faint">“{notes}”</p>}
      </div>

      {truth && (
        <footer className="mt-1 flex items-center gap-2 border-t border-line-soft pt-3.5">
          <FieldLabel>Answer key</FieldLabel>
          <Chip tone="var(--color-ink)">{truth.category}</Chip>
          <Chip tone={TIER[truth.tier]?.tone ?? "var(--color-ink)"}>{truth.tier}</Chip>
          {truth.acceptable_tiers && truth.acceptable_tiers.length > 1 && (
            <span className="text-[11px] text-ink-faint">
              ok: {truth.acceptable_tiers.join(", ")}
            </span>
          )}
        </footer>
      )}
    </article>
  );
}

function ApplicantsTab({ data }: { data: DatasetPayload }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {data.applicants.map((a) => (
        <ApplicantCard key={applicantId(a)} applicant={a} truth={data.ground_truth[applicantId(a)]} />
      ))}
    </div>
  );
}

// --- inventory -------------------------------------------------------------

function DeviceCard({ device }: { device: DatasetDevice }) {
  const tier = device.tier ? TIER[device.tier] : undefined;
  const specEntries = Object.entries(device.specs ?? {});
  return (
    <article className="card card-lift rise flex flex-col gap-3 rounded-card border border-line bg-surface p-4">
      <header className="flex items-center justify-between gap-2">
        <span className="tnum text-sm font-medium text-ink">{device.id}</span>
        {tier ? (
          <span
            className="rounded-full px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.1em] text-canvas"
            style={{ backgroundColor: tier.tone }}
          >
            {device.tier}
          </span>
        ) : (
          <Chip>{device.item_type}</Chip>
        )}
      </header>

      {specEntries.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {specEntries.map(([k, v]) => (
            <Chip key={k}>
              {k}: {String(v)}
            </Chip>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between text-[11px] text-ink-faint">
        <Condition value={device.condition} />
        <span className="tnum">{device.available_from}</span>
      </div>

      {(device.location || device.notes) && (
        <p className="text-[11px] text-ink-faint">
          {device.location}
          {device.location && device.notes ? " · " : ""}
          {device.notes}
        </p>
      )}
    </article>
  );
}

function InventoryTab({ data }: { data: DatasetPayload }) {
  const groups = useMemo(() => {
    const byType = new Map<string, DatasetDevice[]>();
    for (const d of data.inventory) {
      (byType.get(d.item_type) ?? byType.set(d.item_type, []).get(d.item_type)!).push(d);
    }
    return [...byType.entries()].sort(
      (a, b) =>
        (ITEM_TYPE_ORDER.indexOf(a[0]) + 1 || 99) - (ITEM_TYPE_ORDER.indexOf(b[0]) + 1 || 99),
    );
  }, [data.inventory]);

  return (
    <div className="flex flex-col gap-10">
      {groups.map(([type, devices]) => (
        <section key={type} className="flex flex-col gap-3.5">
          <div className="flex items-center gap-3">
            <span className="font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-ink-soft">
              {type}
            </span>
            <span className="tnum text-[11px] text-ink-faint">{devices.length}</span>
            <span className="h-px flex-1 bg-line-soft" />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {devices
              .slice()
              .sort((a, b) => a.id.localeCompare(b.id))
              .map((d) => (
                <DeviceCard key={d.id} device={d} />
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}

// --- ground truth ----------------------------------------------------------

function GroundTruthTab({ data }: { data: DatasetPayload }) {
  const rows = useMemo(() => {
    const entries = Object.entries(data.ground_truth);
    const order = sortScenarios(entries.map(([, v]) => v.scenario));
    return entries.sort((a, b) => order.indexOf(a[1].scenario) - order.indexOf(b[1].scenario));
  }, [data.ground_truth]);

  return (
    <div className="card overflow-x-auto rounded-card border border-line bg-surface">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-line bg-subtle text-left">
            {["Applicant", "Scenario", "Category", "Tier", "Acceptable tiers"].map((h) => (
              <th
                key={h}
                className="px-4 py-3 font-mono text-[10px] font-medium uppercase tracking-[0.16em] text-ink-soft"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([id, label]) => (
            <tr key={id} className="border-b border-line-soft last:border-0">
              <td className="tnum px-4 py-3 text-ink">{id}</td>
              <td className="px-4 py-3 text-ink-soft">
                {SCENARIO_LABELS[label.scenario] ?? label.scenario}
              </td>
              <td className="px-4 py-3">
                <Chip tone="var(--color-ink)">{label.category}</Chip>
              </td>
              <td className="px-4 py-3">
                <Chip tone={TIER[label.tier]?.tone ?? "var(--color-ink)"}>{label.tier}</Chip>
              </td>
              <td className="tnum px-4 py-3 text-ink-faint">
                {(label.acceptable_tiers ?? [label.tier]).join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// --- page ------------------------------------------------------------------

export default function DatasetViewer() {
  const [source, setSource] = useState<ModelKey>("rag");
  const [datasets, setDatasets] = useState<string[]>([]);
  const [dataset, setDataset] = useState<string>("sample-v1");
  const [tab, setTab] = useState<Tab>("applicants");
  const [data, setData] = useState<DatasetPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Dataset list from the chosen backend (falls back to a sensible default).
  useEffect(() => {
    let cancelled = false;
    fetchDatasets(source)
      .then((ds) => {
        if (cancelled || !ds.length) return;
        setDatasets(ds);
        setDataset((cur) => (ds.includes(cur) ? cur : ds[0]));
      })
      .catch(() => {
        if (!cancelled) setDatasets((cur) => (cur.length ? cur : ["sample-v1"]));
      });
    return () => {
      cancelled = true;
    };
  }, [source]);

  // The dataset payload itself, refetched whenever source or dataset changes.
  useEffect(() => {
    if (!dataset) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchDataset(source, dataset)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setData(null);
          setError(e.message);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [source, dataset]);

  const counts = data
    ? {
        applicants: data.applicants.length,
        inventory: data.inventory.length,
        ground: Object.keys(data.ground_truth).length,
      }
    : { applicants: 0, inventory: 0, ground: 0 };

  const TABS: { key: Tab; label: string; count: number }[] = [
    { key: "applicants", label: "Applicants", count: counts.applicants },
    { key: "inventory", label: "Inventory", count: counts.inventory },
    { key: "ground", label: "Answer key", count: counts.ground },
  ];

  return (
    <div className="mx-auto max-w-[1180px] px-6 sm:px-10">
      <TopBar />

      <main>
        {/* hero */}
        <section className="pt-10 sm:pt-16">
          <p className="font-mono text-[11px] uppercase tracking-[0.24em] text-ink-faint">
            Shared dataset
          </p>
          <h1 className="mt-3 font-display text-hero text-ink">Sample data</h1>
          <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-ink-soft">
            The applicants, the device inventory, and the answer key every run is scored
            against.
          </p>
        </section>

        {/* controls: source backend + dataset */}
        <div className="mt-10 flex flex-wrap items-end gap-6">
          <div className="flex flex-col gap-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">
              Source
            </span>
            <div className="flex gap-1 rounded-lg border border-line bg-surface p-1">
              {(["ai", "rag"] as ModelKey[]).map((m) => {
                const active = source === m;
                return (
                  <button
                    key={m}
                    onClick={() => setSource(m)}
                    aria-pressed={active}
                    className="min-h-9 rounded-md px-3.5 py-1.5 text-[13px] transition-colors"
                    style={{
                      backgroundColor: active ? MODEL_ACCENT[m] : "transparent",
                      color: active ? "var(--color-canvas)" : "var(--color-ink-soft)",
                    }}
                  >
                    {MODEL_LABELS[m]}
                  </button>
                );
              })}
            </div>
          </div>

          <label className="flex flex-col gap-2">
            <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">
              Dataset
            </span>
            <div className="relative">
              <select
                value={dataset}
                onChange={(e) => setDataset(e.target.value)}
                disabled={datasets.length === 0}
                className="min-h-11 appearance-none rounded-lg border border-line bg-surface py-2.5 pl-4 pr-11 font-mono text-sm text-ink transition-colors hover:border-ink/30 disabled:opacity-50"
              >
                {datasets.length === 0 && <option>{dataset || "loading…"}</option>}
                {datasets.map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
              <span
                className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-ink-faint"
                aria-hidden
              >
                ↓
              </span>
            </div>
          </label>
        </div>

        {/* tabs */}
        <div className="mt-10 flex flex-wrap gap-6 border-b border-line">
          {TABS.map((t) => {
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                aria-current={active ? "page" : undefined}
                className={`-mb-px flex items-baseline gap-1.5 border-b-2 pb-3 text-sm transition-colors ${
                  active
                    ? "border-ink text-ink"
                    : "border-transparent text-ink-faint hover:text-ink-soft"
                }`}
              >
                {t.label}
                <span className="tnum text-[11px] text-ink-faint">{t.count}</span>
              </button>
            );
          })}
        </div>

        {/* body */}
        <div className="mt-8">
          {error && (
            <div className="rounded-xl border border-signal/40 bg-signal-soft/60 p-4">
              <p className="font-mono text-[11px] font-medium uppercase tracking-[0.14em] text-signal">
                Could not load dataset
              </p>
              <p className="mt-1.5 font-mono text-xs leading-relaxed text-ink">{error}</p>
            </div>
          )}

          {loading && !data && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3" aria-busy="true">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="sweep h-44 rounded-card bg-subtle" />
              ))}
            </div>
          )}

          {data && !error && (
            <>
              {tab === "applicants" && <ApplicantsTab data={data} />}
              {tab === "inventory" && <InventoryTab data={data} />}
              {tab === "ground" && <GroundTruthTab data={data} />}
            </>
          )}
        </div>

        <footer className="mt-20 mb-16 border-t border-line-soft pt-5 text-xs text-ink-faint">
          Read-only from the {MODEL_LABELS[source]} backend · answer-key labels derived from LGT
          precedent, pending human validation.
        </footer>
      </main>
    </div>
  );
}
