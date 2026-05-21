"""Process-global token-bucket rate limiters.

Gemini's free tier limits *requests per minute* (gen 15 RPM, embed ~100 RPM),
not tokens — so the failure mode is bursting past the RPM cap, not exhausting
TPM. These limiters block *before* a request is sent, smoothing bursts into a
steady stream that stays under the cap, instead of firing fast and eating 429s.

Defaults sit safely under the caps and are overridable via env:
  ASRA_RATELIMIT_GENERATION_RPM (default 12, under the 15 cap)
  ASRA_RATELIMIT_EMBEDDING_RPM  (default 80, under the ~100 cap)
  ASRA_RATELIMIT_BURST          (default 1)

The bucket capacity (burst) is deliberately small and *independent* of the
RPM: a bucket sized to the full RPM would allow a one-minute burst of up to
~2x RPM (initial fill + refill) and blow the cap. With burst=1, the worst case
in any rolling minute is burst + RPM tokens, which stays under the real limit.
"""
from __future__ import annotations

import os
import threading
import time


class _Bucket:
    """A simple token bucket. acquire() blocks until a token is available.

    ``rpm`` sets the sustained refill rate; ``burst`` sets the max number of
    requests that may fire back-to-back before pacing kicks in.
    """

    def __init__(self, rpm: float, burst: float = 1.0) -> None:
        self.capacity = max(1.0, burst)
        self.tokens = self.capacity
        self.rate = max(1e-6, rpm / 60.0)  # tokens per second
        self.ts = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        with self.lock:
            while True:
                now = time.monotonic()
                self.tokens = min(
                    self.capacity, self.tokens + (now - self.ts) * self.rate
                )
                self.ts = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                time.sleep((1.0 - self.tokens) / self.rate)


_buckets: dict[str, _Bucket] = {}
_reg_lock = threading.Lock()


def _bucket(name: str, default_rpm: float) -> _Bucket:
    with _reg_lock:
        b = _buckets.get(name)
        if b is None:
            try:
                rpm = float(
                    os.environ.get(f"ASRA_RATELIMIT_{name.upper()}_RPM", default_rpm)
                )
            except ValueError:
                rpm = default_rpm
            try:
                burst = float(os.environ.get("ASRA_RATELIMIT_BURST", "1"))
            except ValueError:
                burst = 1.0
            b = _Bucket(rpm, burst)
            _buckets[name] = b
        return b


def wait_generation() -> None:
    """Block until a generation request slot is free."""
    _bucket("generation", 12.0).acquire()


def wait_embedding() -> None:
    """Block until an embedding request slot is free (one token per item)."""
    _bucket("embedding", 80.0).acquire()
