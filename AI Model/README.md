# ASRA — AI Strategic Resource Allocator (MVP)

A matching engine that pairs technology applicants with donated hardware
for **Let's Get Together (LGT)**. No web frontend, no database, no auth —
this is a defensible MVP for stakeholder demo, with everything LGT will
want to tune wired up as named constants rather than buried in code.

- Python 3.11+
- Google **Gemini 2.5 Flash Lite** via the official `google-genai` SDK
- Pure-functional scoring in [0, 1]; **fit is a hard gate, not a score**
- CLI (`python -m asra_matcher ...`) and FastAPI shim (`asra_matcher.api`)

---

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in GEMINI_API_KEY
```

The engine runs **without** a key — every LLM call has a deterministic
fallback so the demo never crashes on a missing key or transient API
failure. Set `GEMINI_API_KEY` to unlock the parsing, tier recommendation,
and natural-language explanation paths.

## Run

```bash
# Interactive intake (8 questions, ESL-friendly)
python -m asra_matcher intake --inventory sample_data/inventory.json

# Non-interactive: run a saved applicant JSON
python -m asra_matcher match sample_data/applicants/app-FC-newcomer-jobsearch.json \
    --inventory sample_data/inventory.json

# FastAPI server
uvicorn asra_matcher.api:app --reload --port 8000
# POST /match            { "applicant": {...}, "inventory": [...] }
# POST /intake/parse     { "q1": "...", "q2": "...", ... }
# GET  /health
```

## Test

```bash
pytest -v                       # 53 unit + e2e tests, mocked LLM
pytest -v -m integration        # live Gemini calls (requires GEMINI_API_KEY)
```

## Pipeline

```
Applicant
   │  (splitter.split — one Application per category in `purpose`)
   ▼
Application[]
   │  for each Application:
   │     1. fit_gate          — hard exclude on rules / software / accessibility
   │     2. compute_all       — efficiency, timing, priority, condition
   │     3. composite         — weighted sum (see §Tunable knobs)
   │     4. rank, top-2
   ▼
ApplicationResult[]  (one per category)
   │  pick the application whose #1 has the highest composite
   ▼
FinalMatchResult: selected_application + top-2 + LLM explanations
                  + discarded_applications (the worse-matched splits)
```

## Project layout

```
asra_matcher/
  taxonomy.py     — Category, DeviceTier, ItemType, Urgency, TechAccess enums
  models.py       — Pydantic: IntakeAnswers, Applicant, Application, Device,
                    ScoreBreakdown, MatchResult, ApplicationResult, FinalMatchResult
  rules.py        — Direct-linking tier rules; software-capability map
  scoring.py      — Pure functions: fit_gate / efficiency / timing /
                    priority / condition; WEIGHTS composite
  splitter.py     — Multi-category Applicant -> N Applications
  llm.py          — Gemini wrapper (recommend_tier, explain_matches,
                    parse_intake) + deterministic fallbacks + audit log
  intake.py       — Interactive 8-question terminal flow
  engine.py       — Orchestration
  cli.py          — argparse CLI: `intake` and `match`
  api.py          — FastAPI: /match, /intake/parse, /health
sample_data/
  inventory.json          — 20 fake devices across tiers, mobile, peripherals
  applicants/             — 8 sample applicants covering A1-A3, B, C, D, F, F+C
tests/                    — 53 deterministic + 2 integration tests
logs/                     — llm_audit.jsonl is written here
intake_sessions/          — parsed applicants saved here by `intake`
```

---

## What the LLM does (and what it doesn't)

The engine is deterministic everywhere it can be. The LLM is consulted for
exactly three narrow tasks:

| Task | Used when | Falls back to |
|------|-----------|---------------|
| **Tier recommendation** | A3 / C with multiple allowed tiers | Conservative pick: T2 if allowed, else T3, else T1 |
| **Match explanation** | Top-2 results, after ranking is locked | Templated "Device X is a T_ device in condition Y/5 …" sentence |
| **Intake parsing** | Free-text Q1, Q3, Q5, Q6, Q8 | Heuristic parser (number words, keyword matching, regex for year-in-Canada) |

The LLM **never** changes the ranking; it only writes the human-readable
rationale that the LGT reviewer reads alongside the score breakdown.

Every prompt + response is appended to `logs/llm_audit.jsonl` for
post-hoc review.

---

## Tunable knobs

Every constant LGT is likely to revisit lives in a single file. **None of
these require a refactor to change** — they are named constants, not
buried magic numbers. The headings below mirror §11 of the spec.

### Composite weights — `asra_matcher/scoring.py::WEIGHTS`

| Knob | Default | Rationale |
|---|---|---|
| `WEIGHTS["priority"]` | 0.35 | Most important: who needs it most. |
| `WEIGHTS["timing"]` | 0.25 | High but secondary: device ready when applicant needs it. |
| `WEIGHTS["condition"]` | 0.20 | Devices in better shape last longer in service. |
| `WEIGHTS["efficiency"]` | 0.20 | Discourages over-allocation; equal to condition deliberately. |

> **Stakeholder question (§11.3):** is the priority/timing/condition/
> efficiency order correct? Fit is a hard gate; should priority
> dominate this far, or should LGT instead weight timing 0.30?

### Urgency windows — `asra_matcher/taxonomy.py::URGENCY_WINDOW_DAYS`

| Urgency | Days | Maps to applicant answer |
|---|---|---|
| critical | 7 | "This week" |
| high | 30 | "Within a month" |
| medium | 60 | "1-3 months" |
| low | 90 | "Flexible" |

> Adjustable per intake season (e.g., shorten 'low' to 60 in
> back-to-school months).

### Priority formula — `asra_matcher/scoring.py`

| Constant | Default | Rationale |
|---|---|---|
| `URGENCY_BASE` (critical/high/medium/low) | 1.00 / 0.75 / 0.50 / 0.25 | Linear ladder, easy to explain to reviewers. |
| `BONUS_NO_TECH` | +0.10 | An applicant with no device at all jumps ahead of one with a slow laptop. |
| `BONUS_LARGE_HOUSEHOLD` | +0.05 | Families share — small boost. |
| `LARGE_HOUSEHOLD_THRESHOLD` | 3 | What counts as "large". |
| `BONUS_B_OR_C_CATEGORY` | +0.05 | Healthcare / employment seen as marginally higher social urgency. |
| `BONUS_LONG_WAITLIST` | +0.05 | Anti-starvation: a 60-day-old request gets a nudge. |
| `LONG_WAITLIST_THRESHOLD_DAYS` | 60 | Spec §11.5 — confirm with LGT. |
| `PENALTY_REPEAT_WORKING` | −0.10 | First-time applicants favoured if your old device still works. |

> **Stakeholder question (§11.4):** does a student get priority over a
> senior? Does a family get priority over a single user? Right now NO
> category gets absolute priority — every bonus is small and additive.
> LGT may want to reweight (e.g., +0.10 for D Seniors year-round on a
> social-isolation argument).

### Efficiency formula — `asra_matcher/scoring.py::efficiency_score`

Current: `1 − over_allocation_ranks / 2`. Linear, so T1-given-to-T3 = 0,
T2-given-to-T3 = 0.5, exact match = 1.0.

> **Stakeholder question (§11.1):** alternatives worth piloting —
> steeper penalty (drop to −0.5 for max over-alloc so it actively
> outweighs other bonuses); inventory-aware penalty (scale by remaining
> T1 stock). Wait for 1-2 weeks of real allocation data before tuning.

### Software-capability map — `asra_matcher/rules.py`

`HEAVY_SOFTWARE_T1` and `MEDIUM_SOFTWARE_T2` are simple keyword sets.
Adding a tool (e.g., Figma Desktop, MATLAB Online) is a one-line edit.

### Direct-linking rules — `asra_matcher/rules.py::DIRECT_LINKING`

Hard per-category tier sets. Editing the dict updates allowed tiers,
the fit gate, and the engine in one shot. A3 and C are intentionally
left as the full set so the LLM (or its deterministic fallback) can
narrow them based on intake.

### Long-horizon condition penalty — `asra_matcher/scoring.py::condition_score`

Seniors (D) and Newcomers (F) get an extra −0.10 if device condition
< 3. Tunable; LGT may instead want a hard exclusion of condition < 2
for these categories.

### Variables we did **not** collect (Open Question §11.2)

These are deliberately out of scope for the MVP but should be
discussed before production:

- Geographic distance between donor location and applicant
- Language match (device OS / keyboard layout vs. `language_preference`)
- Household size as distinct from `shared_user_count`
- Donor-specified recipient preferences
- Rural / remote location bonus (would need a new Q8 field)

---

## What the demo proves

1. **All 53 unit + e2e tests pass** in the deterministic (no-LLM) mode.
2. The interactive intake collects the exact 8 LGT-framework questions,
   parses free text via the LLM (with heuristic fallback), and produces
   a validated `Applicant`.
3. For a multi-category applicant `[F, C]` the splitter produces two
   Applications, scores both, picks the better-matched one, and reports
   the discarded split to the reviewer.
4. CLI and FastAPI surfaces both return the same `FinalMatchResult`.
5. Every weight, threshold, and bonus that LGT will want to tune lives
   in a named constant, listed above.

## Demo (multi-category newcomer + job-search)

Interactive (`python -m asra_matcher intake`):

> Q1 — "myself, recently arrived from Iran and looking for work" → `who_needs_it`
> Q2 — "2, 5" → `purpose = [C, F]`
> Q4 — "1, 3, 2" → web/email + documents + video calls
> Q5 — "Zoom, Microsoft Word"
> Q6 — "two of us, only have a phone right now" → `shared_user_count=2, current_tech_access=phone_only`
> Q7 — "2" → `urgency=high`
> Q8 — "I arrived in 2025, age 32, currently unemployed" → `year_arrived_canada=2025, age_range=25-40`

Result (identical via `python -m asra_matcher match`):

```
Applicant: demo-FC-applicant
Selected category: C  (top composite: 0.965)
#1  DEV-T2-003  T2 laptop, condition 5/5, available 2026-05-18
                composite 0.965  priority 0.90  timing 1.00  condition 1.00  efficiency 1.00
#2  DEV-T2-001  T2 desktop, condition 4/5, available 2026-05-12
                composite 0.925  priority 0.90  timing 1.00  condition 0.80  efficiency 1.00
Discarded:
  - Category F: best composite 0.925 (device DEV-MOB-001)
```
