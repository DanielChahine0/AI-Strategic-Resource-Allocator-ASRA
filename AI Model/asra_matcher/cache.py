"""Persistent on-disk cache for Gemini generation + embedding responses.

Keyed by a content hash, so re-running the same evaluation on unchanged inputs
costs *zero* API calls — the dominant lever against free-tier rate limiting,
where the same applicants are scored repeatedly.

Configuration (env):
  ASRA_LLM_CACHE_DISABLE  — set to 1/true/yes to bypass the cache entirely.
  ASRA_LLM_CACHE_DIR      — cache location (default ./.asra_cache).

The cache stores JSON; values must be JSON-serialisable (str / list / dict).
All disk errors are swallowed — a cache miss is always safe.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def _enabled() -> bool:
    return os.environ.get("ASRA_LLM_CACHE_DISABLE", "").strip().lower() not in {
        "1",
        "true",
        "yes",
    }


def _dir() -> Path:
    return Path(os.environ.get("ASRA_LLM_CACHE_DIR", "./.asra_cache"))


def make_key(*parts: Any) -> str:
    """Stable content hash over the given parts."""
    h = hashlib.sha256()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def get(kind: str, key: str) -> Any | None:
    """Return the cached value for (kind, key), or None on miss/disabled."""
    if not _enabled():
        return None
    p = _dir() / kind / f"{key}.json"
    try:
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))["value"]
    except Exception:
        return None


def put(kind: str, key: str, value: Any) -> None:
    """Store value under (kind, key). No-op when disabled; errors are ignored."""
    if not _enabled():
        return
    p = _dir() / kind / f"{key}.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"value": value}, default=str), encoding="utf-8")
    except Exception:
        pass
