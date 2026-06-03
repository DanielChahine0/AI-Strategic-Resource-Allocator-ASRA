"""Real-time console logging for watching the engine work.

Everything the engine does with Gemini — each retrieval, each generation call,
its outcome, and every fall-back decision — is emitted here to **stderr** so it
shows up live in the terminal (and in run.sh's ``.run-logs/rag-model.log``).
This is deliberately separate from the structured JSONL audit log
(``logs/llm_audit.jsonl``), which is for after-the-fact analysis; this stream
is for *watching the engine think* while it runs.

Verbosity is controlled by ``ASRA_LOG_LEVEL`` (default ``INFO``):
  * INFO  — one line per Gemini call outcome + per-applicant eval rows + the
            big banner when quota runs out. (the default; what you usually want)
  * DEBUG — also prints prompt sizes, cache hits, and retrieval counts.
  * WARNING — only failures and fall-backs.
"""

from __future__ import annotations

import logging
import os
import sys

_CONFIGURED: set[str] = set()


def get_logger(tag: str = "engine") -> logging.Logger:
    """Return a process-wide logger that writes straight to stderr.

    ``tag`` distinguishes the two backends in a shared terminal (``ai`` / ``rag``).
    The handler is attached once and ``propagate`` is disabled so lines are not
    duplicated through uvicorn's root logger.
    """
    name = f"asra.{tag}"
    logger = logging.getLogger(name)
    if name not in _CONFIGURED:
        level_name = os.environ.get("ASRA_LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level_name, logging.INFO))
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.propagate = False
        _CONFIGURED.add(name)
    return logger


def short(msg: object, n: int = 220) -> str:
    """Collapse whitespace and truncate a (possibly huge) message for one log line."""
    text = " ".join(str(msg).split())
    return text if len(text) <= n else text[: n - 1] + "…"
