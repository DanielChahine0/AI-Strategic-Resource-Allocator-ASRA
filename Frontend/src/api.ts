import type { EvalResult, ModelKey } from "./types";

const ENDPOINTS: Record<ModelKey, string> = {
  ai: import.meta.env.VITE_AI_API ?? "http://localhost:8000",
  rag: import.meta.env.VITE_RAG_API ?? "http://localhost:8001",
};

export const MODEL_LABELS: Record<ModelKey, string> = {
  ai: "AI Model",
  rag: "RAG Model",
};

export async function fetchDatasets(model: ModelKey): Promise<string[]> {
  const res = await fetch(`${ENDPOINTS[model]}/eval/datasets`);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  const data = await res.json();
  return data.datasets ?? [];
}

export async function runEvaluation(
  model: ModelKey,
  dataset: string,
  limit?: number,
): Promise<EvalResult> {
  let res: Response;
  try {
    res = await fetch(`${ENDPOINTS[model]}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset, limit: limit ?? null }),
    });
  } catch {
    throw new Error(
      `Could not reach ${MODEL_LABELS[model]} at ${ENDPOINTS[model]}. Is the server running?`,
    );
  }
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(`${MODEL_LABELS[model]} returned ${res.status}: ${detail.slice(0, 200)}`);
  }
  return (await res.json()) as EvalResult;
}
