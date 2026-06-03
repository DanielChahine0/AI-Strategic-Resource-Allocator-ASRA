import { Link, useLocation } from "react-router-dom";

const NAV = [
  { to: "/impact", label: "Impact" },
  { to: "/inventory", label: "Inventory" },
];

/**
 * Quiet, shared masthead row: wordmark on the left, two nav pills on the
 * right. Deliberately spare — the page title below carries the weight.
 */
export default function TopBar() {
  const { pathname } = useLocation();
  return (
    <header className="flex items-center justify-between gap-4 py-6">
      <Link to="/impact" className="flex items-baseline gap-2.5">
        <span className="font-mono text-xs font-medium uppercase tracking-[0.34em] text-ink">
          ASRA
        </span>
        <span className="hidden text-[13px] text-ink-faint sm:inline">
          Allocation Bench
        </span>
      </Link>
      <nav className="flex items-center gap-1" aria-label="Primary">
        {NAV.map((n) => {
          const active = pathname.startsWith(n.to);
          return (
            <Link
              key={n.to}
              to={n.to}
              aria-current={active ? "page" : undefined}
              className={`flex min-h-9 items-center rounded-full px-3.5 text-[13px] transition-colors ${
                active ? "bg-ink text-canvas" : "text-ink-soft hover:text-ink"
              }`}
            >
              {n.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
