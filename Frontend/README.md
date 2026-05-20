# Frontend — Model Comparison

A Vite + React + TypeScript + Tailwind app that runs both ASRA matching engines
over the same labelled dataset and shows them side by side.

Route: **`/compare`** (the app redirects `/` → `/compare`).

## What it does

- Pick a dataset, then **Run both models** — dispatches `POST /evaluate` to the
  AI Model and the RAG Model **in parallel**, with **independent loading and
  error state per model** (one can fail or lag without blocking the other).
- **Summary cards** per model: accuracy (category + tier vs. ground truth),
  confidence, explanation quality, fallback rate, token totals, wall time.
- **Per-match ledger**: one row per scenario, joined across the two models.
  Rows where the models chose a different category / tier / device are flagged
  `diverges` with a coral rule. Click a row to expand both rationales, the cited
  applicant anchors, RAG grounding citations, runner-up, and token breakdown.

## Running it

The two engines run as separate FastAPI apps on separate ports. From each
model directory (note: the venv console scripts have stale shebangs after the
repo was renamed, so invoke uvicorn via `python -m`):

```bash
# Terminal 1 — AI Model on :8000
cd "../AI Model" && .venv/bin/python -m uvicorn asra_matcher.api:app --port 8000

# Terminal 2 — RAG Model on :8001
cd "../RAG Model" && .venv/bin/python -m uvicorn asra_matcher.api:app --port 8001

# Terminal 3 — frontend
cd Frontend && npm install && npm run dev   # http://localhost:5173/compare
```

Endpoints are configured in `.env` (copy from `.env.example`):

```
VITE_AI_API=http://localhost:8000
VITE_RAG_API=http://localhost:8001
```

## Notes on the numbers

- **Tokens are live only when each backend has a `GEMINI_API_KEY`.** Without one,
  the engines run deterministic fallbacks and report 0 tokens (the card shows
  "no live key → deterministic path").
- **Accuracy** is measured against each model's
  `sample_data/ground_truth.json`, derived from the LGT precedent decisions and
  **pending human validation**.
- **RAG grounding** (citations, tier recommendations) only works once the Chroma
  KB is ingested: `POST /admin/reingest` on the RAG server. On an empty KB the
  RAG model falls back to conservative tiers and emits no citations.
