import type { ImpactReport, InventoryResponse, ModelKey } from "./types";

const ENDPOINTS: Record<ModelKey, string> = {
  ai: import.meta.env.VITE_AI_API ?? "http://localhost:8000",
  rag: import.meta.env.VITE_RAG_API ?? "http://localhost:8001",
};

export const MODEL_LABELS: Record<ModelKey, string> = {
  ai: "AI Model",
  rag: "RAG Model",
};

// --- tiny client cache -----------------------------------------------------
// Stale-while-fresh: a result is reused for `ttlMs` and concurrent callers
// share the same in-flight promise (dedupe), so flipping between views or
// double-rendering never re-hits the network. A rejected fetch is evicted so
// the next call retries. Pass force=true to bypass (e.g. a manual refresh).
type CacheEntry = { at: number; value: Promise<unknown> };
const _cache = new Map<string, CacheEntry>();

function cached<T>(key: string, ttlMs: number, fn: () => Promise<T>, force = false): Promise<T> {
  const now = Date.now();
  const hit = _cache.get(key);
  if (!force && hit && now - hit.at < ttlMs) return hit.value as Promise<T>;
  const value = fn().catch((e) => {
    _cache.delete(key);
    throw e;
  });
  _cache.set(key, { at: now, value });
  return value as Promise<T>;
}

/** Drop cached responses (all, or just one key prefix). */
export function invalidateCache(prefix?: string): void {
  if (!prefix) return _cache.clear();
  for (const k of _cache.keys()) if (k.startsWith(prefix)) _cache.delete(k);
}

export async function fetchInventory(
  model: ModelKey,
  force = false,
): Promise<InventoryResponse> {
  return cached(
    `inventory:${model}`,
    60_000,
    async () => {
      let res: Response;
      try {
        res = await fetch(`${ENDPOINTS[model]}/inventory`);
      } catch {
        throw new Error(`Could not reach ${MODEL_LABELS[model]} at ${ENDPOINTS[model]}.`);
      }
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`${MODEL_LABELS[model]} returned ${res.status}: ${detail.slice(0, 200)}`);
      }
      return (await res.json()) as InventoryResponse;
    },
    force,
  );
}

export async function runImpact(
  model: ModelKey,
  area: string | null,
  force = false,
): Promise<ImpactReport> {
  // Cached for 5 min keyed by (model, area): re-opening the view is instant and
  // costs no new tokens; a manual "Run again" passes force=true.
  return cached(
    `impact:${model}:${area ?? "all"}`,
    5 * 60_000,
    async () => {
      let res: Response;
      try {
        res = await fetch(`${ENDPOINTS[model]}/impact`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ area, group_by: "area", batch_size: 10 }),
        });
      } catch {
        throw new Error(`Could not reach ${MODEL_LABELS[model]} at ${ENDPOINTS[model]}.`);
      }
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        throw new Error(`${MODEL_LABELS[model]} returned ${res.status}: ${detail.slice(0, 200)}`);
      }
      return (await res.json()) as ImpactReport;
    },
    force,
  );
}
