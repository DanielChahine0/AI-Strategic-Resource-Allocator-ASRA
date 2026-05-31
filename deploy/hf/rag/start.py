#!/usr/bin/env python3
"""HF Space entrypoint for the ASRA RAG backend.

Guarantees the Chroma index exists before serving, then launches the API.

- If the index was baked into the image at build time, the check passes and the
  idempotent ``ingest`` re-embeds nothing (it only touches chunks whose content
  hash changed), so this is effectively instant and needs no network.
- If the index is missing (e.g. no GEMINI_API_KEY build secret was configured),
  it is rebuilt now using the runtime ``GEMINI_API_KEY`` env var.

Either way the FastAPI app comes up with a populated vector store.
"""
from __future__ import annotations

import os
import subprocess
import sys


def _index_chunk_count() -> int:
    try:
        from asra_matcher.rag import store
        return sum(store.count(ns) for ns in store.NAMESPACES)
    except Exception as exc:  # store not initialised, chroma not built, etc.
        print(f"[start] index check failed ({exc!r}); treating as empty")
        return 0


def _ingest(*args: str) -> int:
    # Fixed argv list (no shell, no user input) — not a command-injection sink.
    cmd = [sys.executable, "-m", "asra_matcher", "ingest", *args]
    print(f"[start] running: {' '.join(cmd)}")
    return subprocess.run(cmd, check=False).returncode


count = _index_chunk_count()
if count > 0:
    print(f"[start] Chroma index present ({count} chunks) — idempotent top-up")
    _ingest()
else:
    if not os.environ.get("GEMINI_API_KEY"):
        print("[start] WARNING: empty index AND no GEMINI_API_KEY — RAG retrieval "
              "will be degraded until a key is set and the Space restarts.")
    else:
        print("[start] Chroma index empty — building from kb/ ...")
        if _ingest("--rebuild") != 0:
            print("[start] WARNING: ingest failed; RAG retrieval will be degraded.")

port = os.environ.get("PORT", "7860")
print(f"[start] launching uvicorn on 0.0.0.0:{port}")
# Replace this process with uvicorn (fixed argv, no shell).
os.execvp(sys.executable, [
    sys.executable, "-m", "uvicorn", "asra_matcher.api:app",
    "--host", "0.0.0.0", "--port", str(port),
])
