"""Embedding client. Wraps Google's gemini-embedding-001 with rate-limit-aware batching.

Free-tier Gemini allows 100 embed requests/minute and each item in a batched
``contents=[...]`` call counts as one request. We default to a small batch
size and a fixed inter-batch sleep that together stay safely under the limit;
on 429 we parse the API's own ``retryDelay`` and wait that long.

The module is import-safe even when google-genai is not installed or the API
key is missing — the client is constructed lazily on first call. Tests
monkeypatch :func:`embed_texts` and never hit the network.
"""
from __future__ import annotations

import os
import re
import time
from collections.abc import Iterable

from .. import cache, ratelimit

_DEFAULT_MODEL = "gemini-embedding-001"

# Rate-limit-friendly defaults for the Gemini free tier.
# Each item in `contents` counts as one quota unit. The shared token-bucket
# limiter (one token per item) keeps us under the ~100 req/min cap, so we no
# longer need a fixed inter-batch sleep — batching is now purely a round-trip
# optimisation.
_BATCH_SIZE = int(os.environ.get("ASRA_EMBED_BATCH_SIZE", "5"))
# Cap on how long we'll wait on a 429 before giving up.
_MAX_RETRY_WAIT_S = float(os.environ.get("ASRA_EMBED_MAX_RETRY_WAIT_S", "120"))


def _model() -> str:
    return os.environ.get("ASRA_EMBEDDING_MODEL", _DEFAULT_MODEL)


def _client():
    """Lazy-construct the google-genai client. Imported here so tests can mock."""
    from google import genai  # type: ignore

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set; cannot call the embedding API."
        )
    return genai.Client(api_key=api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts.

    Each text is cached on disk by content hash, so repeated query strings —
    common across the multiple retrievals in one match, and across re-runs of
    the same eval — are embedded once and reused with no API call. Only the
    cache misses (deduplicated) hit the network, batched and rate-limited.
    """
    if not texts:
        return []

    results: dict[int, list[float]] = {}
    miss_index: dict[str, list[int]] = {}
    for i, t in enumerate(texts):
        cached = cache.get("embed", cache.make_key(_model(), t))
        if cached is not None:
            results[i] = cached
        else:
            miss_index.setdefault(t, []).append(i)

    miss_texts = list(miss_index.keys())
    if miss_texts:
        vectors = _embed_uncached(miss_texts)
        for t, vec in zip(miss_texts, vectors, strict=False):
            cache.put("embed", cache.make_key(_model(), t), vec)
            for i in miss_index[t]:
                results[i] = vec

    return [results[i] for i in range(len(texts))]


def _embed_uncached(texts: list[str]) -> list[list[float]]:
    """Embed cache-miss texts: batched calls, one rate-limit token per item."""
    out: list[list[float]] = []
    for batch in _chunks(texts, _BATCH_SIZE):
        for _ in batch:
            ratelimit.wait_embedding()
        out.extend(_embed_batch_with_retry(batch))
    return out


def _chunks(items: list[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


_RETRY_DELAY_RE = re.compile(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s")


def _parse_retry_delay(exc: Exception) -> float | None:
    """Pull the ``retryDelay`` field out of a Gemini 429 error message."""
    msg = str(exc)
    m = _RETRY_DELAY_RE.search(msg)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _embed_batch_with_retry(batch: list[str]) -> list[list[float]]:
    try:
        return _embed_batch(batch)
    except Exception as exc:
        msg = str(exc)
        if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
            wait = _parse_retry_delay(exc) or 60.0
            # Add a small safety margin so we don't retry on the exact second.
            wait = min(_MAX_RETRY_WAIT_S, wait + 2.0)
            print(f"[embed] rate-limited; sleeping {wait:.1f}s and retrying...")
            time.sleep(wait)
            return _embed_batch(batch)
        # Other transient failures: short pause and retry once.
        time.sleep(0.5)
        return _embed_batch(batch)


def _embed_batch(batch: list[str]) -> list[list[float]]:
    client = _client()
    # google-genai exposes `models.embed_content` taking a list. Each result has
    # `.values` for the embedding vector.
    resp = client.models.embed_content(model=_model(), contents=batch)
    # Newer SDK returns `.embeddings` (list of `ContentEmbedding`).
    embeds = getattr(resp, "embeddings", None) or resp.get("embeddings")  # type: ignore[union-attr]
    vectors: list[list[float]] = []
    for e in embeds:
        values = getattr(e, "values", None)
        if values is None and isinstance(e, dict):
            values = e.get("values") or e.get("embedding")
        vectors.append(list(values))
    return vectors
