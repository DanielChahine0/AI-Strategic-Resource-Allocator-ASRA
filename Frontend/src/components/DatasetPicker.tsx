interface Props {
  datasets: string[];
  value: string;
  onChange: (v: string) => void;
  onRun: () => void;
  running: boolean;
}

export default function DatasetPicker({ datasets, value, onChange, onRun, running }: Props) {
  return (
    <div className="flex flex-wrap items-end gap-4">
      <label className="flex flex-col gap-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">
          Dataset
        </span>
        <div className="relative">
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={running || datasets.length === 0}
            className="min-h-11 appearance-none rounded-lg border border-line bg-surface py-2.5 pl-4 pr-11 font-mono text-sm text-ink transition-colors hover:border-ink/30 disabled:opacity-50"
          >
            {datasets.length === 0 && <option>loading…</option>}
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

      <button
        onClick={onRun}
        disabled={running || !value}
        className="min-h-11 rounded-lg bg-ink px-6 py-2.5 text-sm font-medium text-canvas transition-all hover:bg-ink/90 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40"
      >
        {running ? "Running…" : "Run comparison"}
      </button>
    </div>
  );
}
