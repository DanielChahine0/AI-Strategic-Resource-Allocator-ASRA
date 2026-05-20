# Frontend (placeholder)

The planned web interface for ASRA. **Not implemented yet.**

Intended scope:

- **Applicant intake** — a guided, ESL-friendly form mirroring the CLI intake
  flow (the same questions the engines parse today).
- **Reviewer dashboard** — surfaces the LGT staff member's recommended device,
  the runner-up, the score breakdown, and the LLM explanation (with cited
  grounding documents in the RAG Model).

Until this is built, both matching engines are exercised through their CLI
(`python -m asra_matcher ...`) and the optional FastAPI endpoints
(`/match`, `/intake/parse`, `/health`) that a frontend would call. See the
[AI Model](../AI%20Model/README.md) and [RAG Model](../RAG%20Model/README.md)
READMEs for the API contracts.
