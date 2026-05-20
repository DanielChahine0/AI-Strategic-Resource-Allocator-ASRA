# ASRA — AI Strategic Resource Allocator

A matching-engine prototype that pairs technology applicants with donated
hardware for **Let's Get Together (LGT)**, built as part of the Riipen / ASRA
project. Given an applicant's needs (collected through a short, ESL-friendly
intake) and a pool of donated devices, the engine recommends the best-fit
device with a transparent, auditable rationale.

This repository holds **three programs** — two independent implementations of
the matching engine plus a placeholder for the user interface:

| Program | What it is | Status |
|---|---|---|
| [`AI Model/`](AI%20Model/) | Matching engine: deterministic rules + scoring, with **Gemini** used for three narrow tasks (intake parsing, tier recommendation, explanations). | ✅ Working MVP (53 tests) |
| [`RAG Model/`](RAG%20Model/) | Same engine, evolved into a **retrieval-augmented** version: a ChromaDB knowledge base grounds every LLM call so each allocation cites the documents behind it. | ✅ Working MVP (32 tests) |
| [`Frontend/`](Frontend/) | Web UI for intake + reviewer dashboard. | 🚧 Placeholder — not yet implemented |

> **Why two engines?** They are two prototype approaches to the same problem,
> kept side by side so LGT can compare them. The **AI Model** is the leaner,
> faster baseline. The **RAG Model** trades setup cost (a local vector store)
> for *grounded, citable* decisions — every recommendation points back to a
> category definition, tier spec, policy, or past-decision document the LGT
> team can audit. Both share the same core idea: **fit is a hard gate, scoring
> is pure-functional, and the LLM never overrides the rules.**

---

## How matching works (shared by both engines)

```
Applicant
   │  splitter — one Application per category in `purpose` (e.g. [F, C])
   ▼
Application[]
   │  for each:  1. fit gate     — hard exclude on rules / software / accessibility
   │             2. score        — priority, timing, condition, efficiency  (each in [0,1])
   │             3. composite     = 0.35·priority + 0.25·timing + 0.20·condition + 0.20·efficiency
   │             4. rank → top 2
   ▼
Pick the application whose #1 device scores highest
   ▼
Final result: selected device + runner-up + LLM explanation + discarded splits
```

Every weight, threshold, and bonus LGT might want to tune lives in a **named
constant**, not a buried magic number. See each program's README for the full
list of tunable knobs and the open stakeholder questions.

---

## Repository layout

```
matching system prototype/
├── README.md            ← you are here (overview of all three programs)
├── LICENSE
├── .gitignore
├── AI Model/            ← engine #1: deterministic + Gemini  (see AI Model/README.md)
│   ├── asra_matcher/    ← package: taxonomy, models, rules, scoring, llm, engine, cli, api
│   ├── sample_data/     ← inventory.json + 9 sample applicants (A1–F, F+C)
│   └── tests/
├── RAG Model/           ← engine #2: + ChromaDB retrieval  (see RAG Model/README.md)
│   ├── asra_matcher/    ← adds rag/ (ingest, store, embed, retrieve, prompts)
│   ├── kb/              ← markdown knowledge base: categories, tiers, policies, past decisions
│   ├── sample_data/
│   └── tests/
└── Frontend/            ← placeholder for the web UI
```

---

## Prerequisites

- **Python 3.11+**
- A **Gemini API key** is *optional*. Both engines run without one — every LLM
  call has a deterministic fallback, so the demo never crashes on a missing key
  or a transient API error. Set `GEMINI_API_KEY` to unlock LLM parsing, tier
  recommendation, and natural-language explanations.

> ⚠️ **Secrets:** each program reads its key from a local `.env` file, which is
> **gitignored** and must never be committed. Copy `.env.example` → `.env` and
> paste your key in. If you ever expose a key, rotate it in Google AI Studio.

---

## Quick start

### AI Model

```bash
cd "AI Model"
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # then add GEMINI_API_KEY (optional)

# Interactive intake (8 questions) against the sample inventory
python -m asra_matcher intake --inventory sample_data/inventory.json

# Or score a saved applicant non-interactively
python -m asra_matcher match \
    sample_data/applicants/app-FC-newcomer-jobsearch.json \
    --inventory sample_data/inventory.json

# Optional FastAPI server: POST /match, POST /intake/parse, GET /health
uvicorn asra_matcher.api:app --reload --port 8000

pytest -v                       # 53 unit + e2e tests (LLM mocked)
```

### RAG Model

```bash
cd "RAG Model"
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env            # then add GEMINI_API_KEY (optional)

# 1. Build the local vector store from kb/  (creates ./chroma_db, gitignored)
.venv/bin/python -m asra_matcher ingest --rebuild

# 2. Interactive intake (7 questions)
.venv/bin/python -m asra_matcher intake --inventory sample_data/inventory.json

# 3. Or run a saved applicant
.venv/bin/python -m asra_matcher match \
    sample_data/applicants/applicant_FC_multi.json \
    --inventory sample_data/inventory.json

.venv/bin/pytest -v             # 32 tests (LLM + embeddings mocked)
```

Each program's own README has the deep detail: full pipeline, the LLM's exact
role and fallbacks, every tunable knob, and (for the RAG Model) how to extend
the knowledge base.

---

## Frontend

`Frontend/` is a placeholder for the planned web interface (applicant intake +
LGT reviewer dashboard). It is **not implemented yet** — today both engines are
driven through their CLI and the optional FastAPI endpoints, which a frontend
would call.

---

## License

Proprietary — see [`LICENSE`](LICENSE). © 2026 Riipen / ASRA team. All rights
reserved. Internal prototype for stakeholder demo; not for redistribution.
