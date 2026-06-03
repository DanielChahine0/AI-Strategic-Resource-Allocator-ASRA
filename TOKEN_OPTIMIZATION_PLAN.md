# ASRA — Token Optimization & Simplified Matching Plan

**Date:** 2026-06-03
**Goal:** Cut Gemini token usage hard by (a) collapsing intake to 4 questions, (b) doing as
much as possible with deterministic algorithm instead of AI, (c) pulling real refurbished
inventory from Google Sheets, (d) making the free quota go further via key rotation + a
batch pipeline, and (e) surfacing exact token spend at every step.

Decisions locked in with the user:
- **Sheets access:** public **CSV export** (no credentials).
- **Scoring engine:** **replace** the old 8-category / priority / timing / condition engine
  with a simple first-come-first-serve (FCFS) model driven only by Q1–Q4.
- **Free-model scaling:** build **key rotation + a sequential batch pipeline with progress**.
  *Skip* programmatic key creation (Google does not support it — manual only).
- **Models:** apply the simplification to **both AI Model and RAG Model** so the head-to-head
  comparison still works.

---

## 0. The new intake — only 4 questions

| Q | Question | Field | Uses AI? | How it's used |
|---|----------|-------|----------|---------------|
| **Q1** | Computer Type — Ubuntu / Windows / Both | `os_choice` (enum) | **No** | Deterministic **inventory filter** (see §1.2) |
| **Q2** | Main needs for a computer | `main_needs` (text) | **Yes** | Fit signal |
| **Q3** | Software for your computer | `software` (text) | **Partly** | Deterministic capability check first, AI only on unknowns |
| **Q4** | Challenges without a computer + how it will help | `challenge` (text) | **Yes** | Fit / suitability signal |

**These four are the *only* matching criteria.** Everything else (urgency, category, priority,
timing, condition weighting, the 8-way category split, tier recommendation) is **removed**.
Allocation order is **first-come-first-serve** by submission timestamp — no priority scoring,
no AI for ordering.

### Q1 is an OS-capability filter (important)
The Google Sheet has **no OS column**. Refurb PCs get imaged with whatever OS is installed, so
Q1 cannot filter an existing field. We interpret Q1 as a **spec-capability filter**:
- **Ubuntu** → low bar: any working machine (≥4 GB RAM).
- **Windows** → Windows-11-capable bar: ≥8 GB RAM, 64-bit CPU recent enough, ≥64 GB disk.
- **Both** → must satisfy the Windows bar (superset).

Thresholds live in one config constant so LGT can tune them. *(Alternative if LGT prefers: add
an "OS" column to the sheet and filter on it directly — the loader supports either; flagged in
§1.)*

---

## 1. Inventory from Google Sheets (replaces mock JSON)

**New module:** `sheets.py` in **both** `AI Model/asra_matcher/` and `RAG Model/asra_matcher/`
(shared logic; keep one canonical copy and import, or duplicate to match the repo's existing
side-by-side layout).

Sheet: `1Yv-2Awk6wFK0TZxRyI_1yT5QqqRKp2QMn3cU6St6tPE`, gid `1340502618`.
CSV URL: `https://docs.google.com/spreadsheets/d/<id>/export?format=csv&gid=<gid>`

### 1.1 Parsing rules (grounded in the live sheet)
- **Two header rows:** row 1 is section grouping ("Computers", "Disk Information", …) — **skip
  it**; use **row 2** (`LGT Donation ID, Timestamp, ..., Status, ..., Device type, Processor,
  Total RAM Included (GB), Disk Capacity (GB/TB), ...`) as the column names.
- **Status filter — the headline requirement:** keep **only** rows where
  `Status == "Refurbished- ready for distribution"` (exact string from the sheet; note no space
  after the hyphen). Drop `To be refurbished`, `Allocated`, `Recycled`, blank, etc.
- **Real-machine filter:** keep only `Device type ∈ {DESKTOP, LAPTOP}` (and `ALL-IN-ONE` if
  present). Drop component rows: `HARD DRIVE`, `SAS HDD 3.5in`, `RAM`, `OTHER`, `TABLET`,
  `PHONE`, etc.

### 1.2 Column → `Device` mapping
| Sheet column | `Device` field |
|---|---|
| `LGT Donation ID` | `id` |
| `Device type` | `item_type` = computer; `specs.form_factor` = desktop/laptop |
| `Device Condition` (Poor/Fair/Good/Very good/Excellent) | `condition` 1–5 via lookup |
| `Processor` + `Other Processor` | `specs.cpu` |
| `Total RAM Included (GB)` | `specs.ram_gb` (int) |
| `Disk Capacity (GB/TB)` | `specs.storage_gb` (normalize TB→GB) |
| `Disk Type` | `specs.disk_type` |
| `Device Brand` + `Device Model` | `specs.model` / `notes` |
| `Timestamp` | `available_from` |
| `Hub ID` / `Bin ID` | `location` |

`tier` is **derived deterministically** from specs (RAM/CPU/disk) so we keep tier as a capability
label without an LLM call — reuse/inline the existing tier logic from `taxonomy.py`.

### 1.3 Caching + resilience
- Fetch CSV with `requests`/`urllib`, **TTL cache** (e.g. 5 min) in memory + on-disk snapshot
  (`.asra_cache/inventory.csv`) as fallback when the sheet is unreachable.
- New endpoint **`GET /inventory`** → returns parsed, filtered refurbished devices (+ counts:
  total rows, refurbished, after-machine-filter) so the frontend stops using mock data.
- `eval.py` inventory load (currently `inventory.json`, eval.py:147) switches to the Sheets
  loader, with the JSON kept only as an offline test fixture.

---

## 2. Replace the scoring engine (FCFS + Q1–Q4 only)

**Files:** `engine.py`, `scoring.py`, `models.py`, `splitter.py` in both models.

### 2.1 New data model (`models.py`)
Replace the 8-field `IntakeAnswers` with a lean one:
```python
class IntakeAnswers:
    os_choice: Literal["ubuntu", "windows", "both"]   # Q1
    main_needs: str                                    # Q2
    software: str                                      # Q3
    challenge: str                                     # Q4
    submitted_at: datetime                             # FCFS ordering only
```
Delete `purpose`, `urgency`, `a3_subtrack`, `shared_user_count`, `current_tech_access`,
`waitlist_days`, `prior_device_status`, etc. Drop `splitter.py`'s category split entirely
(one applicant = one application).

### 2.2 New pipeline (`engine.py`)
```
load refurbished inventory (Sheets)
  → Q1 deterministic OS-capability filter        [no tokens]
  → Q3 deterministic software-capability check    [no tokens for known software]
  → rank candidates deterministically (capability fit, condition, efficiency)
  → take top-N candidates (N small, e.g. 3)
  → ONE AI call: score Q2/Q3/Q4 fit + explanation for those N   [tokens here only]
  → pick best; FCFS handled at the batch level by submission order
```
No `recommend_tier` call. No priority/timing/condition weighting. The only LLM call per
applicant is a **single combined "fit + explain"** over a tiny candidate set.

### 2.3 New weighting (§ "update the weighting of 2,3,4")
Composite is just the three questions, normalized, kept dead simple:
```
fit = w2*needs_fit + w3*software_fit + w4*challenge_fit     (defaults 0.4 / 0.35 / 0.25)
```
- `software_fit` is computed **deterministically** when every named package is in the existing
  `software_capability_matrix` — AI is only invoked for unrecognized software. This is a big
  token saver and directly answers "some questions don't need AI."
- Weights live in one constant block so they're trivially tunable.

---

## 3. Token reduction levers (the core goal)

Concrete, ordered by impact:

1. **Kill the `recommend_tier` LLM call** — tier is now derived from specs. *(−1 call/applicant
   in RAG for A3/C cases.)*
2. **Pre-filter before prompting** — Q1 OS filter + status filter + machine filter shrink the
   candidate set sent to the model from ~200 devices to a handful. Fewer device specs in the
   prompt = fewer prompt tokens.
3. **Cap candidates at top-N (default 3)** sent to the AI, chosen by the deterministic pre-rank.
4. **One combined call** for parse-needs + fit + explanation instead of separate
   `parse_intake` / `recommend` / `explain` calls.
5. **Deterministic software check** — no AI when all software is known (§2.3).
6. **Trim prompts:** drop urgency/category/shared-user boilerplate (those fields are gone);
   send only id + 3–4 spec fields per candidate; shorten system prompt.
7. **RAG retrieval diet:** lower `k_per_namespace` (4→2) and the per-chunk render cap
   (1200→~600 chars) in `rag/retrieve.py` / `rag/prompts.py`; restrict namespaces to
   `software` + `tiers` (the only ones still relevant once categories are gone).
8. **Cap `ASRA_MAX_OUTPUT_TOKENS`** lower (explanations are 2–3 sentences; 1024→256).
9. **Cache** keyed on normalized (Q2|Q3|Q4 + candidate-id set) — identical re-runs cost 0.

**Expected:** from ~3 calls × ~1.5–2k tokens (~5k/applicant) down to **≤1 call × a few hundred
tokens**, with many applicants resolved **fully deterministically (0 tokens)** when software is
known and one candidate clearly wins.

---

## 4. Per-step token observability ("show tokens at every single step")

**Files:** `llm.py` (token capture), `obslog.py`, `eval.py`, `api.py`, frontend.

- Extend the existing context-local token ledger (`start_token_capture`, llm.py:100) from a
  single total to a **per-step list**: `[{step: "software_fit", calls, cache_hits, fallbacks,
  prompt_tokens, output_tokens}, ...]` plus a running cumulative total.
- Steps to label: `os_filter` (0, deterministic), `software_check` (0 or AI), `fit_explain`,
  `intake_parse` (if still used). Deterministic steps are logged with `tokens: 0` so the UI can
  show "0 tokens — handled by algorithm."
- `obslog.py`: emit one INFO line per step with its token cost and the running total.
- API responses (`/match`, `/evaluate`) include the per-step breakdown.
- **Frontend:** new "Token ledger" panel on a match (extend `RowDetail.tsx` and
  `SummaryCards.tsx`, which already show totals) listing each step, its token cost, whether it
  was algorithm/AI/cache/fallback, and the cumulative total.

---

## 5. Free-model scaling — key rotation + batch pipeline

### 5.1 Key rotation (`llm.py`)
- Read a **pool**: `GEMINI_API_KEYS` (comma-separated) or `GEMINI_API_KEY_1..N`.
- A `KeyPool` rotates round-robin; on a `429`/quota error mark the current key
  `exhausted_until = now + retry_seconds` (the retry parser already exists, llm.py:207) and move
  to the next live key. Only fall back to deterministic templates when **all** keys are cooling.
- `model_status()` (llm.py:304) reports per-key state + which key served the call.
- **Not building** automated key *creation* — Google has no supported API for free-tier keys;
  document the manual steps (one key per Cloud project) instead.

### 5.2 Batch pipeline with progress
- New `batch.py` + endpoint **`POST /batch`** taking a list of applicants and a grouping
  (`by_area` / `by_submission_order` / `none`) and a `batch_size`.
- Runs applicants **sequentially in batches**, FCFS by `submitted_at`, spreading calls across
  the key pool, with per-batch and cumulative **token totals**.
- **Progress streaming:** Server-Sent Events (or a `GET /batch/{id}/progress` poll) emitting
  `{done, total, current_applicant, tokens_so_far, keys_state}` so the frontend shows a live
  progress bar.
- "Batch by category/area/urgency": since urgency/category are gone, batching is by **area**
  (applicant location / Etobicoke flag) or plain submission order. Documented accordingly.

---

## 6. Mock data + Etobicoke impact run

- Rewrite `sample_data_v2/applicants/*.json` so each applicant only has **Q1–Q4 + submitted_at**
  (drop all removed fields). Update `ground_truth.json` to match (acceptable device ids only).
- Update `eval.py` accuracy metrics (eval.py:61) — `category_correct`/`tier_correct` no longer
  exist; replace with `device_acceptable` + `software_satisfied`.
- **Etobicoke set:** add `sample_data_v2/applicants_etobicoke/` (a labelled list of Etobicoke
  applicants) and a one-command run (`run.sh` flag or `python -m asra_matcher batch
  --area etobicoke`) that produces an **impact summary**: N served, devices allocated, tokens
  spent, % resolved with 0 AI. Surface this as an "Impact" view in the frontend.

---

## 7. Frontend — faster fetching + caching + token ledger

**Files:** `Frontend/src/api.ts`, `App.tsx`, `SummaryCards.tsx`, `RowDetail.tsx`, `types.ts`,
new components.

- **Client cache:** wrap fetches in a small SWR-style cache (or add `@tanstack/react-query`):
  cache `/inventory`, `/eval/dataset`, `/status` with stale-while-revalidate; dedupe in-flight
  requests; cache evaluation results in memory keyed by dataset so re-opening is instant.
- **Faster perceived load:** show cached data immediately, revalidate in background; keep the
  existing "both models run in parallel" behavior (App.tsx:53).
- **New types** (`types.ts`): `os_choice`, `main_needs`, `software`, `challenge`, per-step token
  ledger, batch progress, inventory payload. Remove dead fields (urgency/category/etc.).
- **Token ledger UI** (§4) + **batch progress bar** (§5.2) + **Etobicoke impact** view (§6).
- **Live inventory:** `DatasetViewer.tsx` reads `/inventory` (refurbished-only) instead of mock.

---

## 8. Phasing / sequencing

1. **Phase 1 — Sheets loader** ✅ DONE — `sheets.py` + `GET /inventory` in both models,
   public CSV export, status+machine filters, tier derivation, TTL cache + snapshot.
   Verified: 27 refurbished rows → 25 allocatable computers from the live sheet.
2. **Phase 2 — Simplified model** ✅ DONE (as an additive `/allocate` path — see note below).
   New `simple.py` in both models: `SimpleIntake` (Q1–Q4), deterministic OS-capability
   filter (Q1) + software-capability check (Q3), top-N pre-rank, ONE combined
   `llm.fit_and_explain` call (Q2/Q4 fit + explanation). No parse call (free-text Qs fed
   directly), no priority/timing/category/tier-recommendation. RAG variant adds light
   KB retrieval (tiers + software namespaces) and citations.
   Verified end-to-end against the live sheet + Gemini: **1 call/applicant** — AI ≈716
   tokens, RAG ≈1093 (grounded). Offline fallback ranks deterministically. New hermetic
   tests (AI 8, RAG 5); all legacy tests still green (AI 63, RAG 42).
3. **Phase 3 — Token observability** ✅ DONE (API + obslog; frontend panel is Phase 6).
   `SimpleResult.token_steps` lists every step with `kind` (algorithm / ai / cache /
   fallback), input/output/total tokens, and a running `cumulative_total`; `tokens_total`
   is the final cumulative. Deterministic steps (`os_filter`, `software_check`, `prerank`)
   report **0 tokens**; the lone `fit_explain` call carries the spend, measured via a
   ledger-diff helper that never disturbs an outer capture (so the Phase-4 batch runner can
   wrap it). Each step is also logged live via obslog. Verified: os_filter/software/prerank
   = 0, fit_explain = 718 → tokens_total 718. Tests added (AI 73, RAG 48 total, all green).
4. **Phase 4 — Key rotation + batch pipeline** ✅ DONE.
   `keypool.py` (both models): round-robin `KeyPool` over keys discovered from
   `GEMINI_API_KEYS` / `GEMINI_API_KEY_1..N` / `GEMINI_API_KEY`, with per-key cooldown. The
   LLM transport now builds one client per key and, on a 429, parks that key for its retry
   window and rotates to the next live key — only falling back deterministically when every
   key is cooling. Auth-bad keys are parked 1h. `model_status` exposes `keys_total`,
   `keys_live`, and per-key `key_pool` state. `batch.py` + `POST /batch` (both models): FCFS
   runner grouping by area / submission, one token-capture around the whole run for exact
   per-applicant + aggregate attribution, live obslog progress + a `progress_cb` hook for a
   future streaming UI. Verified live: rotation past a bogus key proven (bogus parked ~1h,
   real key served all calls), area grouping + FCFS order + per-applicant tokens correct.
   Tests added (keypool + batch); suites green (AI 81, RAG 56).
   *Not built:* programmatic key **creation** — Google has no supported free-tier key API;
   operators add each key by hand in a separate Cloud project (documented in `keypool.py`).
5. **Phase 5 — Mock data + Etobicoke impact run + eval migration + legacy removal.**
   - **5a — simplified mock data + impact harness** ✅ DONE. New repo-root
     `sample_simple/applicants.json` — 12 mock applicants answering **only Q1–Q4**, tagged by
     GTA area (6 Etobicoke). New `eval_simple.py` (both models) + `POST /impact` runs the
     dataset (optionally one area) through the FCFS batch pipeline against live inventory and
     returns an `ImpactReport` (matched, match_rate, tokens_total, avg, AI-vs-deterministic,
     by_area, by_matched_tier). Verified live: **Etobicoke 6/6 matched, 4553 tokens
     (~759/applicant)**, demanding applicant → T1, rest → T2. Tests added (AI 84, RAG 59).
   - **5b — legacy removal** ✅ DONE. Deleted the priority/category engine in both models —
     `engine.py`, `scoring.py`, `splitter.py`, `intake.py`, `eval.py` (+ RAG `rag/prompts.py`).
     Trimmed `models.py` to `Device` (RAG keeps `RetrievedChunk`/`RagContext`), `rules.py` to
     the software-capability matrix, `llm.py` to the transport + key-pool + `fit_and_explain`
     (removed `recommend_tier`/`explain_matches`/`parse_intake` + their result classes),
     `cli.py` (AI → minimal `allocate`; RAG → `ingest`-only, which `run.sh` needs), and
     `conftest.py`. Removed legacy endpoints (`/match`, `/intake/parse`, `/evaluate`,
     `/eval/*`); the API surface is now `/inventory`, `/allocate`, `/batch`, `/impact`,
     `/status`, `/health` (+ RAG `/admin/reingest`). Deleted the legacy test files.
     **Frontend repointed:** removed `/compare` + `/dataset` and their components; home is now
     **/impact**, plus a new **/inventory** view on `GET /inventory`; trimmed `api.ts`/`types.ts`
     of the eval contracts. Verified: backend suites green (AI 21, RAG 21), both CLIs work,
     live allocate still matches (702 tokens), frontend typecheck + build clean (78 KB gzip).
     The replacement the user chose is now complete — no legacy path remains.
6. **Phase 6 — Frontend caching + token ledger + impact UI** ✅ DONE (impact slice).
   `api.ts` gained a stale-while-fresh in-memory cache (TTL + in-flight dedupe + manual
   `invalidateCache`) wrapping datasets / `/inventory` / `/impact`, so re-opening views is
   instant and costs no new tokens. New typed contracts (`InventoryResponse`, `TokenStep`,
   `BatchItem/Result`, `ImpactReport`). New **/impact route** (Impact.tsx): area selector
   (Etobicoke default), runs `/impact` on AI + RAG in parallel, shows matched/tokens/AI-vs-
   algorithm stats, by-tier breakdown, an AI-vs-RAG token-delta line, and a per-applicant list
   where each row expands to a **`TokenLedger`** showing 0 tokens at the deterministic steps
   and the spend at the lone AI call. Backend tweak: `BatchItem.token_steps` carries the
   per-step ledger so the payload is self-describing. Typecheck + production build clean;
   nav + route wired. (A live browser walkthrough runs via `./run.sh`.)
   *Remaining:* the legacy `/compare` view still reads `/evaluate` — retiring/repointing it
   is bundled with **Phase 5b** (legacy removal).

Each phase is independently shippable; Phases 1–3 deliver most of the token savings.

### Note on Phase 2 sequencing (additive → replace)
The simplified engine landed as a **new `/allocate` endpoint** rather than an in-place
rewrite of `/match`, because the legacy `IntakeAnswers` is shared by `eval.py`, the 62×2
sample applicants, two `ground_truth.json` files, and ~16 tests — mutating it in place would
break `/evaluate` and the whole suite, which the plan defers to Phase 5. Keeping the new path
additive means the repo stays green at every commit. **Phase 5 removes the legacy path**, so
the end state is the full replacement the user chose — reached without a broken intermediate.

---

## 9. Open items / assumptions to confirm

- **Q1 OS filter** is implemented as a spec-capability filter (no OS column in the sheet). If
  LGT would rather add an explicit "OS" column, the loader switches to filter on it — one-line
  change. **(Default: capability filter; confirm the RAM/CPU thresholds with LGT.)**
- **Exact status string** is `"Refurbished- ready for distribution"` (no space after hyphen) —
  match will be whitespace/case-normalized to be safe.
- **API key pool** requires LGT to create N keys in N Google Cloud projects manually; we provide
  a short runbook.
- **Applicant intake source:** this plan assumes applicants still arrive via `/intake` / mock
  data. If LGT has a second sheet/form of real applicants (incl. Etobicoke), point the loader at
  it the same way as inventory.
