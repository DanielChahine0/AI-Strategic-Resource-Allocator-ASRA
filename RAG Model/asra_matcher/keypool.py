"""Round-robin Gemini API-key pool with per-key cooldown.

Free-tier keys carry a small *daily* request cap. Configuring several keys —
each from a different Google Cloud project — multiplies the effective quota: a
key that returns 429 is parked until its retry window passes and the pool
rotates to the next live key, only forcing a deterministic fallback once every
key is cooling.

Keys are discovered from the environment (all sources merged, de-duped, order
preserved):
  GEMINI_API_KEYS       comma/space/newline-separated list (preferred)
  GEMINI_API_KEY_1..N   numbered singletons (N up to 20)
  GEMINI_API_KEY        the original single key

Pure key-selection logic — no network, no SDK — so it is unit testable in
isolation. The LLM wrapper builds one client per key on demand.

NOTE: Google does not offer an API to *create* free-tier keys programmatically;
each key is added by hand in a separate Cloud project. This pool makes the most
of however many keys the operator supplies.
"""
from __future__ import annotations

import os
import re
import threading
import time


def discover_keys() -> list[str]:
    """Merge every configured key source into an ordered, de-duplicated list."""
    keys: list[str] = []
    for chunk in re.split(r"[,\s]+", os.environ.get("GEMINI_API_KEYS", "")):
        if chunk.strip():
            keys.append(chunk.strip())
    for i in range(1, 21):
        v = os.environ.get(f"GEMINI_API_KEY_{i}", "").strip()
        if v:
            keys.append(v)
    single = os.environ.get("GEMINI_API_KEY", "").strip()
    if single:
        keys.append(single)

    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


class KeyPool:
    """Thread-safe round-robin selector over keys, skipping cooling ones."""

    def __init__(self, keys: list[str]):
        self._keys = list(keys)
        self._cool: dict[str, float] = {}   # key -> epoch the cooldown ends
        self._idx = 0
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._keys)

    def has_keys(self) -> bool:
        return bool(self._keys)

    def _now(self) -> float:
        return time.time()

    def acquire(self) -> str | None:
        """Return the next live key (round-robin), or None if all are cooling."""
        with self._lock:
            now = self._now()
            n = len(self._keys)
            for _ in range(n):
                k = self._keys[self._idx % n]
                self._idx += 1
                if self._cool.get(k, 0.0) <= now:
                    return k
            return None

    def mark_cooling(self, key: str, seconds: float) -> None:
        """Park `key` for `seconds` (e.g. a 429 retryDelay or an auth lockout)."""
        with self._lock:
            self._cool[key] = self._now() + max(1.0, float(seconds))

    def live_count(self) -> int:
        with self._lock:
            now = self._now()
            return sum(1 for k in self._keys if self._cool.get(k, 0.0) <= now)

    def all_cooling(self) -> bool:
        return self.has_keys() and self.live_count() == 0

    def status(self) -> list[dict]:
        """Per-key snapshot for the dashboard (keys identified only by last 4)."""
        with self._lock:
            now = self._now()
            out = []
            for k in self._keys:
                until = self._cool.get(k, 0.0)
                out.append(
                    {
                        "key_tail": k[-4:] if len(k) >= 4 else "????",
                        "cooling": until > now,
                        "cooldown_seconds": max(0, round(until - now)) if until > now else 0,
                    }
                )
            return out
