# syntax=docker/dockerfile:1.4
# ASRA — RAG Model backend (Hugging Face Docker Space)
#
# Same data-path contract as the AI image (editable install so parents[2] == /app),
# plus a ChromaDB vector store built from kb/. The index is BAKED at build time
# using GEMINI_API_KEY as a build secret, then a self-healing idempotent ingest
# runs at startup (a no-op when the index is already baked). See start.py.
FROM python:3.11-slim

# build-essential is a safety net for any sdist in the chromadb dependency tree.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# HF Spaces runs as UID 1000 — own the baked index so it stays writable at query time.
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ASRA_CHROMA_PATH=/app/rag_model/chroma_db \
    ASRA_KB_PATH=/app/rag_model/kb

WORKDIR /app

# Engine source (the "RAG Model/" folder, copied in as rag_model/, includes kb/)
# + shared datasets at the repo-root-equivalent.
COPY --chown=user rag_model/       /app/rag_model/
COPY --chown=user sample_data/     /app/sample_data/
COPY --chown=user sample_data_v2/  /app/sample_data_v2/
COPY --chown=user start.py         /app/start.py

# Editable install — keeps asra_matcher at /app/rag_model so the data path holds.
RUN pip install --no-cache-dir --user -e /app/rag_model

# Bake the Chroma index. Non-fatal: if no build secret is configured, start.py
# builds it on first boot using the runtime GEMINI_API_KEY instead.
RUN --mount=type=secret,id=GEMINI_API_KEY,uid=1000 \
    sh -c 'if [ -s /run/secrets/GEMINI_API_KEY ]; then \
             echo "[build] baking Chroma index from kb/..."; \
             GEMINI_API_KEY="$(cat /run/secrets/GEMINI_API_KEY)" \
               python -m asra_matcher ingest --rebuild \
               || echo "[build] ingest failed — start.py will rebuild at runtime"; \
           else \
             echo "[build] no GEMINI_API_KEY build secret — deferring index build to runtime"; \
           fi'

EXPOSE 7860
CMD ["python", "/app/start.py"]
