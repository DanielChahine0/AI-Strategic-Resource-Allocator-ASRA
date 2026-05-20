# ASRA Matcher — RAG Model

A retrieval-augmented matching engine that pairs hardware-donation applicants
with available inventory for **Let's Get Together (ASRA)**. Three layers:

1. **Deterministic rules + scoring** (`rules.py`, `scoring.py`) — pure functions.
2. **Retrieval** (`rag/`) — ChromaDB persistent local store, embeddings via
   Google `text-embedding-004`.
3. **Generation** (`llm.py`) — Gemini 2.5 Flash Lite (`gemini-2.5-flash-lite`)
   via `google-genai`, called only with retrieved context grounding every
   prompt.

Every allocation comes with cited grounding documents the LGT team can audit.
The LLM cannot override the direct-linking rules in `rules.py`.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env
# Edit .env and set GEMINI_API_KEY=...
```

Without a key, the engine still runs — every LLM task has a deterministic
fallback path and the audit log records when a fallback was used.

## Quick start

```bash
# 1. Build the local vector store from kb/
.venv/bin/python -m asra_matcher ingest --rebuild

# 2. Interactive intake against an inventory file
.venv/bin/python -m asra_matcher intake --inventory sample_data/inventory.json

# 3. Non-interactive run against a pre-built applicant JSON
.venv/bin/python -m asra_matcher match \
    sample_data/applicants/applicant_FC_multi.json \
    --inventory sample_data/inventory.json
```

## Project layout

```
asra_matcher/
  taxonomy.py       enums (Category, DeviceTier, ItemType, Urgency)
  models.py         Pydantic schemas (Applicant, IntakeAnswers, Device, ...)
  rules.py          direct-linking rules + fit gate
  scoring.py        priority / timing / condition / efficiency / composite
  splitter.py       multi-category applicant → N applications
  rag/
    ingest.py       walks kb/, chunks, embeds, writes to Chroma
    store.py        one Chroma collection per namespace
    embed.py        text-embedding-004 batched + retry
    retrieve.py     query(text, namespaces, k, filters)
    prompts.py      templates w/ abstain-when-context-thin boilerplate
  llm.py            Gemini wrapper for Task A (tier rec), B (explain), C (parse)
  intake.py         7-question terminal flow w/ ESL-friendly prompts
  engine.py         split → filter → score → rank → RAG-explain → top 2
  cli.py            click CLI (ingest / intake / match)
  api.py            FastAPI: POST /match, /intake/parse, /admin/reingest

kb/                 Source-of-truth knowledge base (markdown w/ YAML frontmatter)
  categories/       A1, A2, A3, B, C, D, E, F
  tiers/            T1, T2, T3, peripherals
  software_capability_matrix.md
  lgt_policies/     multi_category_selection, scoring_weights_rationale
  past_decisions/   13 worked examples spanning all categories

tests/              pytest — rules, scoring, splitter, RAG retrieve, engine e2e
sample_data/        inventory.json (20 items) + 9 applicant JSONs
```

## How the matcher decides

1. **Splitter** — each applicant's `purpose` list becomes one application per
   category. They are scored independently; only the winning application is
   returned.
2. **Fit gate** — per `rules.py`. A1→T3, A2→T2, B→{T2,T3}, D→T3+mobile,
   E→T3, F→T3+mobile. A3 and C are RAG-decided. Software in the capability
   matrix that exceeds a device tier rejects that device hard.
3. **RAG tier narrowing** (A3, C only) — `llm.recommend_tier()` retrieves from
   `categories`, `tiers`, `software`, `decisions`. The LLM picks T1/T2/T3 with
   citations, or abstains → conservative fallback.
4. **Score** — pure functions; composite = `0.35·priority + 0.25·timing +
   0.20·condition + 0.20·efficiency`. Fit is a hard gate, never a weight.
5. **Rank** — top 2 devices per application.
6. **Pick the winning application** by highest composite of its #1.
7. **Explain** — `llm.explain_matches()` writes 2-3 sentences per device,
   citing source filenames. Ranking is locked in before this step.

Every LLM call is appended to `logs/llm_audit.jsonl`.

## Tunable knobs

All values intentionally live in code or `.env`, not in the KB:

| Knob | Location | Default | Rationale |
|---|---|---|---|
| `WEIGHTS` (priority/timing/condition/efficiency) | `scoring.py` | `0.35 / 0.25 / 0.20 / 0.20` | Priority dominates; condition+efficiency are stewardship signals, not urgency signals. |
| `URGENCY_WINDOW_DAYS` | `taxonomy.py` | `critical=7, high=30, medium=60, low=90` | Defines when a device "fails" the timing test for a given urgency. |
| Priority bumps | `scoring.py` | `+0.10` no device, `+0.05` shared≥3, `+0.05` B or C | All derive from the 7 intake fields. |
| `k_per_namespace` (Task A — tier rec) | `llm.recommend_tier()` | `categories=4, tiers=3, software=4, decisions=2` | Concentrated on category and software grounding. |
| `k_per_namespace` (Task B — explain) | `llm.explain_matches()` | `decisions=3, policies=2, tiers=2` | Decisions carry the most precedent; policies justify weight-driven choices. |
| `k_per_namespace` (Task C — parse intake) | `llm.parse_intake()` | `categories=3, software=3` | Tight context for parsing without noise. |
| `CHUNK_TOKENS`, `OVERLAP_TOKENS` | `rag/ingest.py` | `400 / 50` (≈4 chars/token) | Standard RAG defaults; small enough to stay in `gemini-2.5-flash-lite`'s budget. |
| Embedding model | env `ASRA_EMBEDDING_MODEL` | `text-embedding-004` | Matches Google's recommended cost/quality point for short docs. |
| Generation model | env `ASRA_GENERATION_MODEL` | `gemini-2.5-flash-lite` | Lowest-cost Gemini 2.5 family that still handles structured JSON output. |
| Temperatures | `llm.py` | `parse=0.1, tier=0.1, explain=0.4` | Determinism for parsing/decision; small variance for human-readable explanations. |
| Fallback behavior | `llm.py` | conservative tier + deterministic explanation; both logged to `llm_audit.jsonl` | Pipeline never crashes on transient errors or abstentions. |

## Open design questions (stakeholder review)

These are the questions the MVP defers to LGT staff. Each has a working
default so the engine ships; mark them up before launch.

1. **Scoring weight order — is priority > timing > condition = efficiency
   correct?**
   - Default: `priority=0.35, timing=0.25, condition=0.20, efficiency=0.20`.
   - Should timing outrank priority for critical urgencies? Should efficiency
     outrank condition?

2. **Category-vs-category priority — does a senior outrank a student, etc.?**
   - Default: no category beats another. Priority is built from urgency +
     access + share-count + healthcare/employment bump.
   - Should A (education), D (seniors), or F (newcomers) receive a fixed
     multiplier? If so, what ranking?
   - **Known interaction:** the `+0.05` employment/healthcare bump is absorbed
     by the priority clamp when urgency is already critical-with-bumps. A
     critical newcomer-also-job-searcher therefore picks F (first in
     `purpose`), not C. If LGT wants C to win in those cases, lift priority's
     clamp or weight the bump.

3. **Household / family size — does a family outrank a single user?**
   - Default: `shared_user_count ≥ 3` adds `+0.05` to priority.
   - Should we add a household-size field, and should it weight more than
     share-count alone?

4. **Repeat applicants — should someone who received a device 3 years ago be
   deprioritized?**
   - Default: not encoded; every applicant treated as new.
   - Should we add `prior_allocation_date` and a cooldown rule?

5. **Anti-starvation — long waiters get a boost?**
   - Default: not encoded (requires persistent applicant state).
   - Threshold (days) and boost magnitude TBD once persistence ships.

6. **Geography — rural/remote priority?**
   - Default: not collected.
   - Add location/region field? Weighting rationale?

7. **First-come-first-serve fallback — when two applicants tie?**
   - Default: submission timestamp, oldest first.
   - Confirm or specify alternate tiebreak.

8. **Accessibility needs — collect at intake?**
   - Default: not in the current 7 questions.
   - Add as Q8? Affects fit-gate decisions (display size, screen-reader
     compatibility).

9. **Grade 7 — A1 or A2?**
   - Default: A2.
   - Confirm.

## How to extend the KB

The KB is the source of truth. Anything not documented here is invisible to
the LLM, by design.

### Frontmatter convention

Every markdown file under `kb/` starts with:

```markdown
---
namespace: categories | tiers | software | policies | decisions
category: A1 | A2 | A3 | B | C | D | E | F   # optional, used for retrieval filters
tier: T1 | T2 | T3 | OTHER                    # optional, for tier-scoped docs
tags: [free, form, tags]
synthetic: true                                 # only for seeded past-decision examples
last_reviewed: YYYY-MM-DD
---
```

The first paragraph (≤ 80 words) is embedded separately as the primary "summary"
chunk. Subsequent `##` sections each become their own chunk (split further if
they exceed ~400 tokens).

### Adding a policy or decision

1. Drop a `.md` file into `kb/lgt_policies/` or `kb/past_decisions/` with the
   frontmatter above. Use `namespace: policies` or `namespace: decisions`.
2. Re-ingest:

```bash
.venv/bin/python -m asra_matcher ingest
```

The ingest is idempotent — only chunks whose `content_hash` changed are
re-embedded. Use `--rebuild` to wipe and re-embed everything.

### Adding a software entry to the capability matrix

Update **both** `kb/software_capability_matrix.md` (the LLM-visible source)
and the `DEFAULT_SOFTWARE_MIN_TIER` dict in `asra_matcher/rules.py` (the
fit-gate source). Keeping them redundant on purpose: the rules layer must
keep working without the KB ingested.

## Deliverables (demo evidence)

- `scripts/demo_intake_output.txt` — full transcript of an interactive intake
  on a multi-category applicant (newcomer + job-searching). Shows all 7
  prompts, the conditional school follow-up, the saved intake file, the
  splitter discarding the losing application, and the top-2 devices with the
  score breakdown.
- `scripts/demo_pytest_output.txt` — `pytest` summary (32 passed).
- `intake_sessions/` — JSON snapshot of every intake run (gitignored).
- `logs/llm_audit.jsonl` — every LLM call's retrieved chunks, prompt, response,
  and fallback usage (gitignored).

### Without a `GEMINI_API_KEY`

The demo above runs in **fallback mode** — the embedding API and the
generation API both raise. The pipeline catches both, uses heuristic intake
parsing and conservative tier defaults, and surfaces "fallback used" notes on
every match. Set a real key in `.env` to see the RAG layer actually retrieve
from `kb/` and to see Gemini-generated explanations.

## Test plan

```bash
.venv/bin/pytest -v
```

- `test_rules.py` — every category produces the correct allowed-tier set;
  software-vs-tier gating; peripheral rejection.
- `test_scoring.py` — efficiency penalizes over-allocation; timing decays
  past urgency window; priority clamps at 1.0; composite arithmetic.
- `test_splitter.py` — `[F, C]` → two applications.
- `test_rag_retrieve.py` — deterministic-vector embed + fake KB +
  in-memory Chroma; verifies namespace scope, `k` cap, and filter scoping.
- `test_engine_e2e.py` — end-to-end engine runs with the LLM mocked; multi-
  category applicant picks the higher-scoring application; the engine
  returns `[]` for empty inventory.

Integration tests that actually hit Gemini are gated:

```bash
.venv/bin/pytest -m integration
```

(There are no integration tests in the seed — add them under a
`@pytest.mark.integration` decorator and provide `GEMINI_API_KEY`.)
