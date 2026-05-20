interface Props {
  datasets: string[];
  value: string;
  onChange: (v: string) => void;
  onRun: () => void;
  running: boolean;
}

export default function DatasetPicker({ datasets, value, onChange, onRun, running }: Props) {
  return (
    <div className="flex flex-wrap items-end gap-5">
      <label className="flex flex-col gap-1.5">
        <span className="text-[11px] uppercase tracking-[0.18em] text-[var(--color-ink-soft)]">
          Dataset
        </span>
        <div className="relative">
          <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={running || datasets.length === 0}
            className="appearance-none rounded-none border border-[var(--color-ink)] bg-transparent py-2.5 pl-3.5 pr-10 font-mono text-sm text-[var(--color-ink)] focus:outline-none focus:ring-2 focus:ring-[var(--color-ink)] disabled:opacity-50"
          >
            {datasets.length === 0 && <option>loading…</option>}
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

      <button
        onClick={onRun}
        disabled={running || !value}
        className="group relative overflow-hidden rounded-none bg-[var(--color-ink)] px-7 py-2.5 font-mono text-sm font-medium uppercase tracking-[0.16em] text-[var(--color-paper)] transition-transform active:translate-y-px disabled:cursor-not-allowed disabled:opacity-60"
      >
        {running ? "running…" : "▶ Run both models"}
      </button>

      <p className="max-w-xs text-xs leading-relaxed text-[var(--color-ink-soft)]">
        Sends <span className="font-mono">/evaluate</span> to both models at the same time.
        Each one runs the data set on its own list of applicants.
      </p>
    </div>
  );
}
