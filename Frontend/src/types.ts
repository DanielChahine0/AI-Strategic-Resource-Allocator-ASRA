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
  n_scored: number;
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

// Mirrors the /status contract returned by BOTH backends
// (AI Model/asra_matcher/llm.py:model_status and RAG Model equivalent).
export type ModelStateName =
  | "live"
  | "ready"
  | "rate_limited"
  | "auth_error"
  | "no_api_key"
  | "sdk_missing"
  | "degraded";

export interface ModelStatus {
  model: string;
  embedding_model?: string;
  embeddings_ok?: boolean | null;
  provider: string;
  sdk_installed: boolean;
  api_key_configured: boolean;
  state: ModelStateName;
  live: boolean;
  using_fallback: boolean;
  detail: string;
  retry_after_seconds: number | null;
  quota: { limit?: number; quota_id?: string; metric?: string } | null;
  session: {
    total_calls: number;
    successes: number;
    failures: number;
    fallback_rate: number;
    consecutive_failures: number;
  };
  last_success: string | null;
  last_call: string | null;
  last_error: string | null;
  last_error_kind: string | null;
}

// Per-model async state, kept separate so one model can load or fail
// without affecting the other.
export interface ModelRunState {
  status: "idle" | "loading" | "done" | "error";
  result: EvalResult | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Raw labelled dataset, served read-only by GET /eval/dataset/{name} on both
// backends. The two models DIVERGE on the applicant intake shape (the RAG
// model nests `current_tech_access` as an object and `main_usage` as a string;
// the AI model flattens both and adds demographic fields), so the intake type
// stays deliberately loose and the viewer normalizes at render time. Inventory
// and ground-truth shapes are identical across both backends.
// ---------------------------------------------------------------------------

export interface DeviceSpecs {
  cpu?: string;
  ram_gb?: number;
  ssd_gb?: number;
  gpu?: string;
  form?: string;
  size_inches?: number;
  kind?: string;
  [key: string]: unknown;
}

export interface DatasetDevice {
  id: string;
  item_type: string;
  tier: string | null;
  specs: DeviceSpecs;
  condition: number;
  available_from: string;
  location: string | null;
  notes: string | null;
}

// RAG shape; AI uses a plain string enum instead.
export interface CurrentTechAccessObj {
  has_internet?: boolean | null;
  device_situation?: string | null;
  notes?: string | null;
}

export interface DatasetIntake {
  who_needs_it: string;
  purpose: string[];
  main_usage: string | string[];
  software_needed: string[];
  shared_user_count: number;
  urgency: string;
  a3_subtrack?: string | null;
  current_tech_access?: CurrentTechAccessObj | string | null;
  [key: string]: unknown;
}

export interface DatasetApplicant {
  id?: string; // RAG
  applicant_id?: string; // AI
  submitted_at: string;
  notes?: string | null;
  intake: DatasetIntake;
}

export interface GroundTruthLabel {
  scenario: string;
  category: string;
  tier: string;
  acceptable_tiers?: string[];
  acceptable_device_ids?: string[];
}

export interface DatasetPayload {
  dataset: string;
  applicants: DatasetApplicant[];
  inventory: DatasetDevice[];
  ground_truth: Record<string, GroundTruthLabel>;
}
