// Mirrors the shared /evaluate contract returned by BOTH backends
// (AI Model/asra_matcher/eval.py and RAG Model/asra_matcher/eval.py).

export interface TokenUsage {
  input: number;
  output: number;
  total: number;
}

export interface AccuracyResult {
  category_correct: boolean;
  tier_correct: boolean;
  device_acceptable: boolean | null;
  score: number;
}

export interface ExplanationQuality {
  score: number;
  anchors_expected: string[];
  anchors_present: string[];
  cites_applicant_field: boolean;
}

export interface EvalRow {
  applicant_id: string;
  scenario: string;
  chosen_category: string | null;
  chosen_device_id: string | null;
  chosen_tier: string | null;
  composite: number;
  runner_up_device_id: string | null;
  runner_up_composite: number | null;
  tokens: TokenUsage;
  accuracy: AccuracyResult | null;
  confidence: number;
  explanation: string | null;
  explanation_quality: ExplanationQuality | null;
  citations: string[];
  tier_recommendation_confidence: number | null;
  fallback_used: boolean;
  error: string | null;
}

export interface EvalSummary {
  n: number;
  tokens_input_total: number;
  tokens_output_total: number;
  tokens_total: number;
  avg_tokens_per_match: number;
  category_accuracy: number;
  tier_accuracy: number;
  device_accuracy: number;
  mean_accuracy_score: number;
  mean_confidence: number;
  mean_explanation_quality: number;
  fallback_rate: number;
  error_count: number;
}

export interface EvalResult {
  model: "ai" | "rag";
  dataset: string;
  run_id: string;
  wall_time_ms: number;
  rows: EvalRow[];
  summary: EvalSummary;
}

export type ModelKey = "ai" | "rag";

// Per-model async state — kept independent so one model can load or fail
// without affecting the other.
export interface ModelRunState {
  status: "idle" | "loading" | "done" | "error";
  result: EvalResult | null;
  error: string | null;
}
