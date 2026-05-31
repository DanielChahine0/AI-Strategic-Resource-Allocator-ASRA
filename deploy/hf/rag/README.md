---
title: ASRA RAG Model
emoji: 🧩
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
short_description: ASRA retrieval-augmented matching engine (FastAPI + Chroma)
---

# ASRA — RAG Model backend

Private Docker Space serving the **RAG Model** matching engine
(`asra_matcher.api:app`) for the ASRA Model-Comparison frontend.

Every LLM call is grounded in a local ChromaDB knowledge base (`kb/`), baked
into the image at build time. **A `GEMINI_API_KEY` is required** here — the
embedding path has no offline fallback, so retrieval needs the key both to build
the index and to embed queries at request time.

This Space is built and pushed from the monorepo by
`deploy/hf/assemble_and_push.sh`. Do not edit files here by hand — re-run that
script to update.

## Configuration (Settings → Variables and secrets)
| Name | Kind | Value |
|---|---|---|
| `GEMINI_API_KEY` | **secret** | your free Google AI Studio key (also enable it as a **build** secret so the index is baked) |
| `ASRA_CORS_ORIGINS` | variable | your Cloudflare Pages URL, e.g. `https://asra.pages.dev` |

Health check: `GET /health` · Datasets: `GET /eval/datasets`
