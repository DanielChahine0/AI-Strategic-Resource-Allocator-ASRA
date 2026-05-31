---
title: ASRA AI Model
emoji: 🧮
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
short_description: ASRA matching engine API (FastAPI + Gemini)
---

# ASRA — AI Model backend

Private Docker Space serving the **AI Model** matching engine
(`asra_matcher.api:app`) for the ASRA Model-Comparison frontend.

Deterministic rules + scoring, with Gemini used for narrow tasks (intake
parsing, explanations). Runs with or without a key — set `GEMINI_API_KEY` to
serve live LLM output instead of deterministic fallbacks.

This Space is built and pushed from the monorepo by
`deploy/hf/assemble_and_push.sh`. Do not edit files here by hand — re-run that
script to update.

## Configuration (Settings → Variables and secrets)
| Name | Kind | Value |
|---|---|---|
| `GEMINI_API_KEY` | secret | your free Google AI Studio key |
| `ASRA_CORS_ORIGINS` | variable | your Cloudflare Pages URL, e.g. `https://asra.pages.dev` |

Health check: `GET /health` · Datasets: `GET /eval/datasets`
