import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
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

type Tab = "applicants" | "inventory" | "ground";

const MODEL_ACCENT: Record<ModelKey, string> = {
  ai: "var(--color-ai)",
  rag: "var(--color-rag)",
};

const TIER: Record<string, { label: string; tone: string }> = {
  T1: { label: "T1 · High power", tone: "var(--color-ai)" },
  T2: { label: "T2 · Standard", tone: "var(--color-rag)" },
  T3: { label: "T3 · Basic", tone: "var(--color-ink-soft)" },
};

const URGENCY_TONE: Record<string, string> = {
  critical: "var(--color-signal)",
  high: "var(--color-ai)",
  medium: "var(--color-ink-soft)",
  low: "var(--color-ink-soft)",
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
      className="inline-flex items-center border px-2 py-0.5 font-mono text-[11px] leading-tight"
      style={{
        borderColor: tone ?? "var(--color-line)",
        color: tone ?? "var(--color-ink-soft)",
      }}
    >
      {children}
    </span>
  );
}

function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-ink-soft)]">
      {children}
    </span>
  );
}

function Condition({ value }: { value: number }) {
  return (
    <span className="tnum tracking-tight" title={`Condition ${value}/5`}>
      {"●".repeat(value)}
      <span className="text-[var(--color-line)]">{"○".repeat(Math.max(0, 5 - value))}</span>
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
    <article className="card card-lift rise flex flex-col gap-3 border border-[var(--color-line)] bg-[var(--color-paper)] p-5">
      <header className="flex items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <span className="tnum text-[11px] text-[var(--color-ink-soft)]">{id}</span>
          <h3 className="font-[family-name:var(--font-display)] text-lg font-semibold leading-tight">
            {intake.who_needs_it}
          </h3>
        </div>
        {urgency && (
          <span
            className="shrink-0 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-paper)]"
            style={{ backgroundColor: URGENCY_TONE[urgency] ?? "var(--color-ink-soft)" }}
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
        <p className="text-sm leading-relaxed text-[var(--color-ink)]">{usageText(intake.main_usage)}</p>
      </div>

      {intake.software_needed?.length > 0 && (
        <div className="flex flex-col gap-1.5">
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
        <p className="text-sm text-[var(--color-ink)]">
          {techAccessLine(intake.current_tech_access)}
          <span className="text-[var(--color-ink-soft)]">
            {" "}
            · {intake.shared_user_count} {intake.shared_user_count === 1 ? "user" : "users"}
          </span>
        </p>
        {notes && <p className="text-xs italic text-[var(--color-ink-soft)]">“{notes}”</p>}
      </div>

      {truth && (
        <footer className="mt-1 flex items-center gap-2 border-t border-[var(--color-line)] pt-3">
          <FieldLabel>Ground truth</FieldLabel>
          <Chip tone="var(--color-good)">{truth.category}</Chip>
          <Chip tone={TIER[truth.tier]?.tone ?? "var(--color-good)"}>{truth.tier}</Chip>
          {truth.acceptable_tiers && truth.acceptable_tiers.length > 1 && (
            <span className="text-[11px] text-[var(--color-ink-soft)]">
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
    <article className="card card-lift rise flex flex-col gap-2.5 border border-[var(--color-line)] bg-[var(--color-paper)] p-4">
      <header className="flex items-center justify-between gap-2">
        <span className="tnum text-sm font-semibold">{device.id}</span>
        {tier ? (
          <span
            className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-paper)]"
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

      <div className="flex items-center justify-between text-[11px] text-[var(--color-ink-soft)]">
        <Condition value={device.condition} />
        <span className="tnum">{device.available_from}</span>
      </div>

      {(device.location || device.notes) && (
        <p className="text-[11px] text-[var(--color-ink-soft)]">
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
    <div className="flex flex-col gap-8">
      {groups.map(([type, devices]) => (
        <section key={type} className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-ink-soft)]">
              {type}
            </span>
            <span className="tnum text-[11px] text-[var(--color-ink-soft)]">({devices.length})</span>
            <span className="h-px flex-1 bg-[var(--color-line)]" />
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
    return entries.sort(
      (a, b) => order.indexOf(a[1].scenario) - order.indexOf(b[1].scenario),
    );
  }, [data.ground_truth]);

  return (
    <div className="card overflow-x-auto border border-[var(--color-line)] bg-[var(--color-paper)]">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--color-ink)] text-left">
            {["Applicant", "Scenario", "Category", "Tier", "Acceptable tiers"].map((h) => (
              <th
                key={h}
                className="px-4 py-2.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-ink-soft)]"
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([id, label]) => (
            <tr key={id} className="border-b border-[var(--color-line)] last:border-0">
              <td className="tnum px-4 py-2.5 text-[var(--color-ink)]">{id}</td>
              <td className="px-4 py-2.5 text-[var(--color-ink-soft)]">
                {SCENARIO_LABELS[label.scenario] ?? label.scenario}
              </td>
              <td className="px-4 py-2.5">
                <Chip tone="var(--color-ink)">{label.category}</Chip>
              </td>
              <td className="px-4 py-2.5">
                <Chip tone={TIER[label.tier]?.tone ?? "var(--color-ink)"}>{label.tier}</Chip>
              </td>
              <td className="tnum px-4 py-2.5 text-[var(--color-ink-soft)]">
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

  const TABS: { key: Tab; label: string }[] = [
    { key: "applicants", label: `Applicants · ${counts.applicants}` },
    { key: "inventory", label: `Inventory · ${counts.inventory}` },
    { key: "ground", label: `Ground truth · ${counts.ground}` },
  ];

  return (
    <div className="relative z-10 mx-auto max-w-6xl px-6 py-10 sm:px-10 sm:py-14">
      <header className="border-b-2 border-[var(--color-ink)] pb-6">
        <div className="flex items-baseline justify-between">
          <span className="text-[11px] uppercase tracking-[0.3em] text-[var(--color-ink-soft)]">
            ASRA · Sample Dataset
          </span>
          <Link
            to="/compare"
            className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-ink-soft)] underline-offset-4 hover:text-[var(--color-ink)] hover:underline"
          >
            Model comparison →
          </Link>
        </div>
        <h1 className="mt-3 font-[family-name:var(--font-display)] text-5xl font-semibold leading-[0.95] tracking-tight sm:text-6xl">
          Sample Data
        </h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[var(--color-ink-soft)]">
          The data set every test runs on. It has the applicant forms, the list of devices they
          can be matched to, and the right answer for who should get what. Each backend has its
          own list of applicants, so pick a source below.
        </p>
      </header>

      {/* controls: source backend + dataset */}
      <div className="flex flex-wrap items-end gap-6 pt-8">
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-ink-soft)]">
            Source
          </span>
          <div className="flex border border-[var(--color-ink)]">
            {(["ai", "rag"] as ModelKey[]).map((m) => {
              const active = source === m;
              return (
                <button
                  key={m}
                  onClick={() => setSource(m)}
                  className="px-4 py-2.5 font-mono text-sm transition-colors"
                  style={{
                    backgroundColor: active ? MODEL_ACCENT[m] : "transparent",
                    color: active ? "var(--color-paper)" : "var(--color-ink)",
                  }}
                >
                  {MODEL_LABELS[m]}
                </button>
              );
            })}
          </div>
        </div>

        <label className="flex flex-col gap-1.5">
          <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-ink-soft)]">
            Dataset
          </span>
          <div className="relative">
            <select
              value={dataset}
              onChange={(e) => setDataset(e.target.value)}
              disabled={datasets.length === 0}
              className="appearance-none rounded-none border border-[var(--color-ink)] bg-transparent py-2.5 pl-3.5 pr-10 font-mono text-sm text-[var(--color-ink)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)] disabled:opacity-50"
            >
              {datasets.length === 0 && <option>{dataset || "loading…"}</option>}
              {datasets.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
            <span className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-[var(--color-ink-soft)]">
              ▾
            </span>
          </div>
        </label>
      </div>

      {/* tabs */}
      <div className="mt-8 flex flex-wrap gap-1 border-b border-[var(--color-line)]">
        {TABS.map((t) => {
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className="-mb-px border-b-2 px-3 py-2 font-mono text-sm transition-colors"
              style={{
                borderColor: active ? "var(--color-ink)" : "transparent",
                color: active ? "var(--color-ink)" : "var(--color-ink-soft)",
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {/* body */}
      <div className="mt-8">
        {error && (
          <div className="border border-[var(--color-signal)] bg-[color-mix(in_srgb,var(--color-signal)_8%,transparent)] p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[var(--color-signal)]">
              Could not load dataset
            </p>
            <p className="mt-1.5 font-mono text-xs leading-relaxed text-[var(--color-ink)]">{error}</p>
          </div>
        )}

        {loading && !data && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3" aria-busy="true">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="sweep relative h-40 overflow-hidden bg-[var(--color-paper-2)]" />
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

      <footer className="mt-14 border-t border-[var(--color-line)] pt-4 text-[11px] text-[var(--color-ink-soft)]">
        Served read-only from <span className="font-mono">/eval/dataset/{dataset}</span> on the{" "}
        {MODEL_LABELS[source]} backend. Ground-truth labels are derived from the LGT precedent
        decisions and are pending human validation.
      </footer>
    </div>
  );
}
