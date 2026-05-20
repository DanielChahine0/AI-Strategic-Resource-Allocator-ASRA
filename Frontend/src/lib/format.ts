export const pct = (v: number): string => `${Math.round(v * 100)}%`;

export const dec = (v: number | null | undefined, places = 2): string =>
  v === null || v === undefined ? "n/a" : v.toFixed(places);

export const int = (v: number): string => v.toLocaleString("en-US");

export const ms = (v: number): string =>
  v >= 1000 ? `${(v / 1000).toFixed(2)}s` : `${Math.round(v)}ms`;

// Scenario keys are shared across both models so rows can be joined.
export const SCENARIO_ORDER = ["A1", "A2", "A3-arts", "A3-swe", "B", "C", "D", "F", "FC"];

export const SCENARIO_LABELS: Record<string, string> = {
  A1: "Education · K to 6",
  A2: "Education · Gr 8 to HS",
  "A3-arts": "Post-sec · Arts",
  "A3-swe": "Post-sec · Software",
  B: "Healthcare",
  C: "Employment",
  D: "Seniors",
  F: "Newcomers",
  FC: "Newcomer + Work",
};

export function sortScenarios(keys: string[]): string[] {
  return [...keys].sort((a, b) => {
    const ia = SCENARIO_ORDER.indexOf(a);
    const ib = SCENARIO_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
}
