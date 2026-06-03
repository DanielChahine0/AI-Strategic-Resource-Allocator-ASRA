// Contracts for the simplified Q1–Q4 pipeline (both backends).

export type ModelKey = "ai" | "rag";

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

// ---------------------------------------------------------------------------
// Simplified Q1–Q4 pipeline contracts: GET /inventory, POST /impact (both
// backends). The impact report bundles a BatchResult whose items carry the
// per-step token ledger (TokenStep[]) so the UI can show exactly where tokens
// were spent — 0 at the deterministic steps, all of it at the one AI call.
// ---------------------------------------------------------------------------

export interface InventoryResponse {
  devices: DatasetDevice[];
  counts: { raw_rows?: number; refurbished?: number; machines?: number; source?: string };
}

export type TokenStepKind = "algorithm" | "ai" | "cache" | "fallback";

export interface TokenStep {
  step: string;
  kind: TokenStepKind;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cumulative_total: number;
  detail: string;
}

export interface BatchItem {
  applicant_id: string;
  area: string | null;
  group: string;
  matched_device_id: string | null;
  matched_tier: string | null;
  composite: number;
  used_ai: boolean;
  tokens_total: number;
  token_steps: TokenStep[];
  explanation: string | null;
}

export interface KeyState {
  key_tail: string;
  cooling: boolean;
  cooldown_seconds: number;
}

export interface BatchResult {
  total: number;
  batches: number;
  batch_size: number;
  group_by: string;
  groups: Record<string, number>;
  tokens_total: number;
  avg_tokens_per_applicant: number;
  used_ai_count: number;
  fallback_count: number;
  unmatched_count: number;
  wall_time_ms: number;
  items: BatchItem[];
  key_pool: KeyState[];
}

export interface ImpactReport {
  dataset: string;
  area_filter: string | null;
  applicants: number;
  matched: number;
  unmatched: number;
  match_rate: number;
  inventory_available: number;
  tokens_total: number;
  avg_tokens_per_applicant: number;
  resolved_with_ai: number;
  resolved_deterministically: number;
  by_area: Record<string, number>;
  by_matched_tier: Record<string, number>;
  wall_time_ms: number;
  batch: BatchResult;
}

export interface ImpactRunState {
  status: "idle" | "loading" | "done" | "error";
  result: ImpactReport | null;
  error: string | null;
}
