# Logged Hours, AI Strategic Resource Allocator (ASRA)

**Contributor:** Daniel Chahine
**Period:** May 22, 2026 to June 8, 2026
**Total logged:** 20.0 hours

Work spans three repositories:
- **ASRA** (`AI-Strategic-Resource-Allocator-ASRA`), Python AI/RAG matching engines and React model comparison frontend
- **Spring Boot backend** (`spring-boot-salesforce-backend`), Salesforce integration and AI matching service
- **lgt frontend** (`lgt-web-frontend`), admin and web app (Vite and React)

## Summary Table

| # | Task | Description | Date of Work | Time |
|---|------|-------------|--------------|------|
| 1 | ASRA, bootstrap matching system prototype | Stood up the initial ASRA matching engine, including applicant and inventory data models, rules and scoring modules, taxonomy, intake parsing, the Gemini LLM client, and the FastAPI service plus CLI entry points. | May 22, 2026 | 2.0 h |
| 2 | ASRA, eval harness and model comparison frontend | Built the evaluation harness (`eval.py`) with a ground truth dataset, then scaffolded the React and TypeScript comparison UI (ComparisonTable, SummaryCards, RowDetail, DatasetPicker) and a `run.sh` launcher. | May 23, 2026 | 2.0 h |
| 3 | ASRA, head to head UI, status bar, dataset viewer | Added the head to head and peer comparison views and a `/status` endpoint with a live model status bar, plus a full dataset viewer component for inspecting applicants and inventory. | May 24, 2026 | 1.5 h |
| 4 | ASRA, caching, rate limiting and capability matrix fix | Added an LLM response cache and request rate limiters across both engines, switched prompts to structured output, and unified the software to tier capability matrix across the AI and RAG engines (critical correctness fix). | May 26, 2026 | 2.0 h |
| 5 | ASRA, audit remediation, Gemini levers, dep pinning | Resolved the "Do now" audit findings (CI pipeline, eval denominator, API auth, ESLint config, React error boundary), added Gemini token levers (disable thinking, opt in embedding tuning), and pinned dependency majors with README corrections. | May 28, 2026 | 1.5 h |
| 6 | ASRA, UI refresh and comparison polish | Reworked the comparison UI with a new TopBar and restyled components, win and loss palette tokens (AA correct red), colored win and loss pills, centered head to head cost rows, and per match anchor chips. | May 31, 2026 | 1.0 h |
| 7 | ASRA, eval dataset v2 and deployment configs | Generated the expanded `sample_data_v2` evaluation dataset and updated the eval pipelines, then authored Hugging Face Spaces and Cloudflare deploy configs (Dockerfiles, assemble and push scripts, DEPLOY.md). | June 2, 2026 | 1.0 h |
| 8 | ASRA, re architect to simplified matching engine | Refactored the AI Model into a streamlined matching engine with batch processing, an API key pool, observability logging, Google Sheets inventory integration, and a simplified eval path. | June 3, 2026 | 1.5 h |
| 9 | Backend, RAG applicant to item matching endpoint | Implemented on demand admin RAG matching in Spring Boot, including `ApplicationController`, `MatchingService`, `InventoryIngestService`, `ApplicantQueryBuilder`, the `MatchSuggestion` model, and unit tests. | June 4, 2026 | 2.0 h |
| 10 | Backend, AI matcher with Gemini and Google Sheet inventory | Built the AI matching layer, including `GeminiService`, `GoogleSheetInventoryService`, an in memory vector index, the `MatchingController`, match and report models, web client and cache config, and accompanying tests. | June 6, 2026 | 2.0 h |
| 11 | lgt frontend, MatchingTester and admin polling | Added the `MatchingTester` component (with styles) to the lgt web app, wired it into the app, refined admin application polling, and bumped a dependency. | June 6, 2026 | 2.0 h |
| 12 | Backend, SSE streaming and model fallback | Added Server Sent Events streaming for live match progress and a model fallback path, including progress events and listener, an expanded `GeminiService` and `MatchingService`, and security config updates. | June 8, 2026 | 1.5 h |

## Hours by Project

| Project | Hours |
|---------|-------|
| ASRA (AI and RAG engines plus comparison frontend) | 12.5 h |
| Spring Boot backend | 5.5 h |
| lgt frontend | 2.0 h |
| **Total** | **20.0 h** |

## Hours by Date

| Date | Hours |
|------|-------|
| May 22, 2026 | 2.0 h |
| May 23, 2026 | 2.0 h |
| May 24, 2026 | 1.5 h |
| May 26, 2026 | 2.0 h |
| May 28, 2026 | 1.5 h |
| May 31, 2026 | 1.0 h |
| June 2, 2026 | 1.0 h |
| June 3, 2026 | 1.5 h |
| June 4, 2026 | 2.0 h |
| June 6, 2026 | 4.0 h |
| June 8, 2026 | 1.5 h |
| **Total** | **20.0 h** |
