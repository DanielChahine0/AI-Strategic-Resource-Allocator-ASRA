"""Gemini wrapper. Every public function retrieves context before generating.

Design notes
------------
* The LLM never reasons from training-data priors alone. Each task pulls
  retrieved chunks first and stuffs them into the prompt with the abstention
  boilerplate from ``rag/prompts.py``.
* On abstention or transient failure, deterministic fallbacks kick in so the
  pipeline never crashes. Fallbacks are logged.
* Every call is appended to ``logs/llm_audit.jsonl`` — one JSON object per line.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Load .env so GEMINI_API_KEY is available no matter how the engine is entered
# (HTTP server, CLI, tests, ad-hoc scripts) — mirrors the AI Model's llm.py.
# Previously only api.py called load_dotenv(), so any non-server entry point saw
# no key and silently ran on deterministic fallbacks (the "no_api_key" state).
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:  # pragma: no cover — dotenv is optional at runtime
    pass

from pydantic import BaseModel

from . import cache, ratelimit
from .models import RagContext, RetrievedChunk
from .rag import retrieve as retrieve_mod

DEFAULT_GEN_MODEL = "gemini-2.5-flash-lite"
TEMP_PARSE = 0.1
TEMP_TIER = 0.1
TEMP_EXPLAIN = 0.4

# Real-time console logger (stderr). Separate from the JSONL audit log: this one
# narrates each retrieval + Gemini call live so `./run.sh` shows *why* the engine
# is or isn't using the LLM. See asra_matcher/obslog.py.
from .obslog import get_logger, short

_log = get_logger("rag")

# Tracks the rate-limit window we last shouted about, so the big "quota
# exhausted" banner prints once per window instead of once per failed call.
_quota_banner_until: float | None = None


def _max_output_tokens() -> int:
    """Cap output to avoid runaway generations. Generous enough not to truncate
    the small JSON payloads these tasks emit."""
    try:
        return int(os.environ.get("ASRA_MAX_OUTPUT_TOKENS", "1024"))
    except ValueError:
        return 1024


def _model() -> str:
    return os.environ.get("ASRA_GENERATION_MODEL", DEFAULT_GEN_MODEL)


def _thinking_budget() -> int:
    """Token budget for model 'thinking'. 0 disables it (the default for these
    extraction/classification tasks). Override via ASRA_THINKING_BUDGET."""
    try:
        return int(os.environ.get("ASRA_THINKING_BUDGET", "0"))
    except ValueError:
        return 0


def _audit_path() -> Path:
    return Path(os.environ.get("ASRA_LLM_AUDIT_LOG", "./logs/llm_audit.jsonl"))


def _audit(record: dict[str, Any]) -> None:
    p = _audit_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ---------------------------------------------------------------------------
# Token capture (used by the evaluation harness — see asra_matcher.eval)
# ---------------------------------------------------------------------------
#
# The eval runner wraps a single `engine.match()` call in start/read so it can
# attribute Gemini token usage (across the tier-recommendation and explanation
# calls) to one applicant. When no ledger is active — the normal /match path —
# `_record_usage` is a no-op, so production behaviour is unchanged.

import contextvars

_TOKEN_LEDGER: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "asra_token_ledger", default=None
)


def start_token_capture() -> dict:
    """Begin capturing token usage for the current context. Returns the ledger.

    Beyond raw token counts, the ledger distinguishes three LLM outcomes so the
    eval can tell them apart instead of lumping them together as "fallback":
      * ``calls``      — fresh, billed Gemini responses (live LLM).
      * ``cache_hits`` — real prior Gemini responses served from disk (0 new
                         tokens, but genuine LLM output — NOT a fallback).
      * ``fallbacks``  — a deterministic template/heuristic ran because the LLM
                         was unavailable or failed (the only true fallback).
    """
    ledger = {"input": 0, "output": 0, "total": 0, "calls": 0, "cache_hits": 0, "fallbacks": 0}
    _TOKEN_LEDGER.set(ledger)
    return ledger


def read_token_capture() -> dict | None:
    """Return the active ledger (or None if capture was never started)."""
    return _TOKEN_LEDGER.get()


def stop_token_capture() -> None:
    _TOKEN_LEDGER.set(None)


def _note_cache_hit() -> None:
    """Record that one LLM result was served from the disk cache (real LLM
    output, 0 new tokens). No-op when no ledger is active."""
    ledger = _TOKEN_LEDGER.get()
    if ledger is not None:
        ledger["cache_hits"] += 1


def _note_fallback() -> None:
    """Record that one LLM task deterministically fell back (template/heuristic).
    No-op when no ledger is active."""
    ledger = _TOKEN_LEDGER.get()
    if ledger is not None:
        ledger["fallbacks"] += 1


def _record_usage(response: Any) -> None:
    """Add one Gemini response's token counts to the active ledger, if any."""
    ledger = _TOKEN_LEDGER.get()
    if ledger is None:
        return
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return
    pin = int(getattr(usage, "prompt_token_count", 0) or 0)
    pout = int(getattr(usage, "candidates_token_count", 0) or 0)
    total = int(getattr(usage, "total_token_count", 0) or 0) or (pin + pout)
    ledger["input"] += pin
    ledger["output"] += pout
    ledger["total"] += total
    ledger["calls"] += 1


# ---------------------------------------------------------------------------
# Low-level generation
# ---------------------------------------------------------------------------


# One genai.Client per API key, built on demand. The KeyPool decides which key
# to use and parks any that hit a 429 / auth error (see asra_matcher.keypool).
_clients: dict[str, Any] = {}
_keypool: Any | None = None


def _pool():
    """Lazily build the process-wide KeyPool from the environment."""
    global _keypool
    if _keypool is None:
        from . import keypool as _kp

        _keypool = _kp.KeyPool(_kp.discover_keys())
        if len(_keypool) > 1:
            _log.info("Gemini key pool: %d keys configured", len(_keypool))
    return _keypool


def reset_pool() -> None:
    """Drop the cached pool + clients (re-read env on next call). For tests."""
    global _keypool
    _keypool = None
    _clients.clear()


def _client_for(key: str):
    from google import genai  # type: ignore

    c = _clients.get(key)
    if c is None:
        c = genai.Client(api_key=key)
        _clients[key] = c
        _log.info("Gemini client ready — gen=%s embed=%s key=…%s", _model(), _embedding_model(), key[-4:])
    return c


def _client():
    """Backward-compatible client accessor (used by embeddings + probe).

    Returns a client bound to the next live pooled key; raises when none is
    configured/available so callers fall back deterministically.
    """
    key = _pool().acquire()
    if key is None:
        if not _pool().has_keys():
            _log.error("No GEMINI API key configured — running on deterministic fallbacks only")
            raise RuntimeError("GEMINI_API_KEY is not set")
        raise RuntimeError("all Gemini API keys are cooling (rate-limited)")
    return _client_for(key)


def _retry_seconds(msg: str) -> float:
    """Seconds to park a key after a 429, parsed from the error (default 60s)."""
    m = _RETRY_RE.search(msg) or _RETRY_RE2.search(msg)
    return float(m.group(1)) if m else 60.0


# ---------------------------------------------------------------------------
# Live model health (surfaced via the API /status endpoint)
# ---------------------------------------------------------------------------
#
# Outcomes of real Gemini calls are recorded into a process-local state dict
# instead of probing on each status request — a probe would itself consume the
# (small) free-tier quota we are trying to protect. This makes it observable
# whether the engine is serving live LLM output or deterministic fallbacks.

import re as _re


def _embedding_model() -> str:
    return os.environ.get("ASRA_EMBEDDING_MODEL", "gemini-embedding-001")


def _sdk_ok() -> bool:
    try:
        import google.genai  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


_HEALTH: dict[str, Any] = {
    "total_calls": 0,
    "total_success": 0,
    "total_failures": 0,
    "consecutive_failures": 0,
    "last_call_ts": None,
    "last_success_ts": None,
    "last_error": None,
    "last_error_kind": None,     # "rate_limit" | "auth" | "other"
    "rate_limited_until": None,
    "quota": None,               # {"limit", "quota_id", "metric"} parsed from a 429
}

_RETRY_RE = _re.compile(r"retry in ([\d.]+)s", _re.IGNORECASE)
_RETRY_RE2 = _re.compile(r"retryDelay'?:?\s*'?(\d+(?:\.\d+)?)s", _re.IGNORECASE)
_LIMIT_RE = _re.compile(r"limit:\s*(\d+)")
_QUOTA_ID_RE = _re.compile(r"quotaId'?:?\s*'?([A-Za-z0-9\-]+)")
_METRIC_RE = _re.compile(r"quotaMetric'?:?\s*'?([A-Za-z0-9_./\-]+)")

_STATE_DETAIL = {
    "live": "Using live Gemini answers.",
    "ready": "Set up and ready. No calls made yet.",
    "rate_limited": "Out of Gemini quota (error 429). Using backup logic until "
    "the limit resets.",
    "auth_error": "Gemini did not accept the API key. Check GEMINI_API_KEY.",
    "no_api_key": "GEMINI_API_KEY is not set. Using backup logic.",
    "sdk_missing": "The google-genai library is not installed. Using backup logic.",
    "degraded": "Recent Gemini calls are failing. Using backup logic.",
}


def _classify_error(msg: str) -> str:
    low = msg.lower()
    if "429" in msg or "resource_exhausted" in low or "quota" in low:
        return "rate_limit"
    if (
        ("api key" in low and "not valid" in low)
        or "api_key_invalid" in low
        or "permission_denied" in low
        or "401" in msg
        or "403" in msg
    ):
        return "auth"
    return "other"


def _record_success() -> None:
    now = time.time()
    _HEALTH["total_calls"] += 1
    _HEALTH["total_success"] += 1
    _HEALTH["consecutive_failures"] = 0
    _HEALTH["last_call_ts"] = now
    _HEALTH["last_success_ts"] = now
    _HEALTH["last_error"] = None
    _HEALTH["last_error_kind"] = None
    _HEALTH["rate_limited_until"] = None


def _record_failure(exc: Exception) -> None:
    now = time.time()
    msg = str(exc)
    kind = _classify_error(msg)
    _HEALTH["total_calls"] += 1
    _HEALTH["total_failures"] += 1
    _HEALTH["consecutive_failures"] += 1
    _HEALTH["last_call_ts"] = now
    _HEALTH["last_error"] = msg[:500]
    _HEALTH["last_error_kind"] = kind
    if kind == "rate_limit":
        m = _RETRY_RE.search(msg) or _RETRY_RE2.search(msg)
        secs = float(m.group(1)) if m else None
        _HEALTH["rate_limited_until"] = now + (secs if secs else 60.0)
        quota: dict[str, Any] = {}
        if (lm := _LIMIT_RE.search(msg)):
            quota["limit"] = int(lm.group(1))
        if (qm := _QUOTA_ID_RE.search(msg)):
            quota["quota_id"] = qm.group(1)
        if (mm := _METRIC_RE.search(msg)):
            quota["metric"] = mm.group(1)
        _HEALTH["quota"] = quota or None

        # Shout once per rate-limit window so a whole eval run doesn't repeat it.
        global _quota_banner_until
        if _quota_banner_until != _HEALTH["rate_limited_until"]:
            _quota_banner_until = _HEALTH["rate_limited_until"]
            _log.error(
                "🚫 GEMINI QUOTA EXHAUSTED — every call now falls back to "
                "deterministic logic. quota=%s limit=%s model=%s retry≈%ss. "
                "This is the free tier's daily request cap, NOT a code bug.",
                quota.get("quota_id", "?"),
                quota.get("limit", "?"),
                _model(),
                int(secs) if secs else "?",
            )
    elif kind == "auth":
        _log.error(
            "🔑 GEMINI AUTH ERROR — key rejected. Check GEMINI_API_KEY in 'RAG Model/.env'. %s",
            short(msg),
        )
    else:
        _log.error("⚠ GEMINI CALL ERROR [other] — %s", short(msg))


def _iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat()


def model_status(probe: bool = False) -> dict[str, Any]:
    """Structured snapshot of the RAG model's live state — generation model,
    embedding model, whether live or on deterministic fallbacks, quota/retry
    info from the last 429, and this session's call stats.

    Derived from real calls made this session (zero quota cost) unless
    ``probe=True``, which spends one cheap generation call (and one embedding
    call) to confirm both answer right now.
    """
    sdk = _sdk_ok()
    key = _pool().has_keys()
    now = time.time()

    rlu = _HEALTH["rate_limited_until"]
    rate_limited = bool(rlu and rlu > now)

    embeddings_ok: bool | None = None
    if probe and sdk and key and not rate_limited:
        try:
            _generate("Reply with one word.", "OK", temperature=0.0, json_mode=False)
        except Exception:
            pass  # recorded in _HEALTH by the call itself
        try:
            _client().models.embed_content(model=_embedding_model(), contents=["ok"])
            embeddings_ok = True
        except Exception:
            embeddings_ok = False
        rlu = _HEALTH["rate_limited_until"]
        rate_limited = bool(rlu and rlu > now)

    if not sdk:
        state = "sdk_missing"
    elif not key:
        state = "no_api_key"
    elif rate_limited:
        state = "rate_limited"
    elif _HEALTH["last_error_kind"] == "auth":
        state = "auth_error"
    elif _HEALTH["total_calls"] == 0:
        state = "ready"
    elif _HEALTH["consecutive_failures"] > 0:
        state = "degraded"
    else:
        state = "live"

    calls = _HEALTH["total_calls"]
    fallback_rate = (_HEALTH["total_failures"] / calls) if calls else 0.0
    retry_after = max(0, round(rlu - now)) if (rate_limited and rlu) else None

    return {
        "model": _model(),
        "embedding_model": _embedding_model(),
        "embeddings_ok": embeddings_ok,
        "provider": "google-gemini",
        "sdk_installed": sdk,
        "api_key_configured": key,
        "keys_total": len(_pool()),
        "keys_live": _pool().live_count(),
        "key_pool": _pool().status(),
        "state": state,
        "live": state == "live",
        "using_fallback": state
        in ("rate_limited", "auth_error", "no_api_key", "sdk_missing", "degraded"),
        "detail": _STATE_DETAIL.get(state, ""),
        "retry_after_seconds": retry_after,
        "quota": _HEALTH["quota"],
        "session": {
            "total_calls": calls,
            "successes": _HEALTH["total_success"],
            "failures": _HEALTH["total_failures"],
            "fallback_rate": round(fallback_rate, 3),
            "consecutive_failures": _HEALTH["consecutive_failures"],
        },
        "last_success": _iso(_HEALTH["last_success_ts"]),
        "last_call": _iso(_HEALTH["last_call_ts"]),
        "last_error": _HEALTH["last_error"],
        "last_error_kind": _HEALTH["last_error_kind"],
    }


def _generate(
    system: str,
    user: str,
    *,
    temperature: float,
    json_mode: bool = True,
    response_schema: Any = None,
) -> str:
    """Single call to Gemini. Returns raw text. One retry on transient error.

    Responses are cached on disk by content hash (see ``cache``): an identical
    (model, system, user, temperature, json_mode, response_schema) tuple is
    served from cache with no API call. A process-global limiter paces live
    calls under the free-tier RPM cap.

    When ``response_schema`` is set, Gemini constrains output to that shape
    (constrained decoding) so callers can drop the JSON-shape description from
    the prompt entirely.
    """
    from google.genai import types  # type: ignore

    ck = cache.make_key(_model(), system, user, temperature, json_mode, response_schema)
    hit = cache.get("gen", ck)
    if hit is not None:
        _note_cache_hit()
        _log.debug("✓ cache hit (gen) — served from disk, no API call, 0 tokens")
        return hit

    cfg_kwargs: dict[str, Any] = {
        "temperature": temperature,
        "system_instruction": system,
        "max_output_tokens": _max_output_tokens(),
    }
    if json_mode:
        cfg_kwargs["response_mime_type"] = "application/json"
    if response_schema is not None:
        cfg_kwargs["response_schema"] = response_schema
    # Narrow extraction/classification — no model "thinking" (it bills at 4x).
    cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=_thinking_budget())
    cfg = types.GenerateContentConfig(**cfg_kwargs)

    _log.debug(
        "→ Gemini call — system=%d chars, user=%d chars, json=%s, schema=%s",
        len(system), len(user), json_mode, response_schema is not None,
    )

    pool = _pool()
    last_exc: Exception | None = None
    max_tries = max(2, len(pool) + 1)
    transient_retry_used = False

    for _ in range(max_tries):
        key = pool.acquire()
        if key is None:
            last_exc = last_exc or RuntimeError("all Gemini API keys are cooling (rate-limited)")
            break
        try:
            ratelimit.wait_generation()
            resp = _client_for(key).models.generate_content(
                model=_model(), contents=user, config=cfg
            )
            _record_usage(resp)
            _record_success()
            text = resp.text or ""
            cache.put("gen", ck, text)
            um = getattr(resp, "usage_metadata", None)
            _log.info(
                "✓ Gemini OK key=…%s — tokens in=%s out=%s total=%s",
                key[-4:],
                getattr(um, "prompt_token_count", "?"),
                getattr(um, "candidates_token_count", "?"),
                getattr(um, "total_token_count", "?"),
            )
            return text
        except Exception as exc:
            last_exc = exc
            kind = _classify_error(str(exc))
            if kind == "rate_limit":
                secs = _retry_seconds(str(exc))
                pool.mark_cooling(key, secs)
                _log.warning("✗ key …%s rate-limited (429) — cooling %ss, rotating", key[-4:], int(secs))
                continue
            if kind == "auth":
                pool.mark_cooling(key, 3600)
                _log.warning("✗ key …%s rejected (auth) — disabling 1h, rotating", key[-4:])
                continue
            if not transient_retry_used:
                transient_retry_used = True
                _log.warning("✗ Gemini failed [%s] — retrying once: %s", kind, short(exc))
                time.sleep(0.5)
                continue
            break

    assert last_exc is not None
    _record_failure(last_exc)
    raise last_exc


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _parse_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    text = text.strip()
    m = _JSON_FENCE.search(text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        # Best-effort: trim around the outermost braces.
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            try:
                return json.loads(text[first : last + 1])
            except Exception:
                return None
        return None


# Cap on how many retrieved chunks get rendered into a single prompt. The
# context block is the dominant input-token cost per call, and the JSON answer
# typically cites only 1-3 sources, so summing every namespace's k (up to 13 for
# tier recommendation) over-stuffs the prompt. Override via env.
def _max_context_chunks() -> int:
    try:
        return int(os.environ.get("ASRA_MAX_CONTEXT_CHUNKS", "6"))
    except ValueError:
        return 6


def _prune_chunks(
    chunks: list[RetrievedChunk],
    *,
    top_n: int | None = None,
    min_similarity: float = 0.0,
) -> list[RetrievedChunk]:
    """Dedupe identical chunks returned by overlapping namespace queries and
    keep the globally most-similar ``top_n`` (default: ``_max_context_chunks``).

    Trims redundant retrieval context before it is billed as generation input
    tokens, without touching ``retrieve.query`` (whose per-call ``k`` semantics
    other callers/tests rely on)."""
    if top_n is None:
        top_n = _max_context_chunks()
    seen: set[tuple[str, str]] = set()
    deduped: list[RetrievedChunk] = []
    for c in sorted(chunks, key=lambda x: x.similarity, reverse=True):
        if c.similarity < min_similarity:
            continue
        key = (c.source_path, c.text)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    return deduped[:top_n]


# ---------------------------------------------------------------------------
# Simplified flow — single combined "fit + explain" call (Q1–Q4 model)
# ---------------------------------------------------------------------------
#
# Mirror of the AI Model's fit_and_explain, but grounded: it retrieves a few
# tier/software-matrix chunks so the scores and rationale cite the KB. Q1 (OS)
# and the software-capability check stay deterministic in asra_matcher.simple;
# this is the only token spend (one generation + the retrieval embeddings).

_FIT_SYSTEM = (
    "You help a nonprofit match donated, refurbished computers to applicants, "
    "using ONLY the provided context (tier definitions and the software "
    "capability matrix) plus the device specs. For EACH candidate device, return "
    "needs_fit and challenge_fit in [0,1] and a concrete 1–2 sentence rationale "
    "that cites the applicant's words, the device specs, and the source files it "
    "relied on. Do not invent specs."
)

_FIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "assessments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "device_id": {"type": "string"},
                    "needs_fit": {"type": "number"},
                    "challenge_fit": {"type": "number"},
                    "explanation": {"type": "string"},
                    "citations": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["device_id", "needs_fit", "challenge_fit", "explanation"],
            },
        }
    },
    "required": ["assessments"],
}


def _clamp01(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def fit_and_explain(
    main_needs: str,
    software: str,
    challenge: str,
    devices: list[Any],
    *,
    retrieve_fn=None,
    generate_fn=None,
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Score + explain a small candidate set in one grounded call.

    Returns ``(by_device_id, used_ai)`` where each value is
    ``{"needs_fit", "challenge_fit", "explanation", "citations"}``. On any
    failure (or no key/SDK) returns neutral 0.6 scores with a deterministic
    template and ``used_ai=False``.
    """
    if not devices:
        return {}, False

    def _fallback() -> tuple[dict[str, dict[str, Any]], bool]:
        out: dict[str, dict[str, Any]] = {}
        for d in devices:
            tier = d.tier.value if getattr(d, "tier", None) else d.item_type.value
            out[d.id] = {
                "needs_fit": 0.6,
                "challenge_fit": 0.6,
                "explanation": (
                    f"Device {d.id} is a {tier} machine in condition {d.condition}/5 — "
                    "a reasonable match scored without the language model."
                ),
                "citations": [],
            }
        return out, False

    if not (_sdk_ok() and os.environ.get("GEMINI_API_KEY")):
        _note_fallback()
        _log.info("· fit_and_explain: LLM unavailable → neutral scores for %d device(s)", len(devices))
        return _fallback()

    # Light retrieval: tier definitions + software matrix only (token diet).
    retrieve_fn = retrieve_fn or retrieve_mod.query
    chunks = []
    try:
        chunks += retrieve_fn(main_needs, namespaces=["tiers"], k_per_namespace=2)
        if software:
            chunks += retrieve_fn(software, namespaces=["software"], k_per_namespace=2)
    except Exception as exc:
        _log.warning("· fit_and_explain: retrieval failed → ungrounded call: %s", short(exc))
        chunks = []
    chunks = _prune_chunks(chunks, top_n=3)
    ctx = RagContext(task="fit_and_explain", chunks=chunks)

    blocks: list[str] = []
    for d in devices:
        tier = d.tier.value if getattr(d, "tier", None) else "n/a"
        blocks.append(f"--- Device {d.id} ---\ntier: {tier}, condition: {d.condition}/5\nspecs: {d.specs}")
    user = (
        f"Context:\n{ctx.render()}\n\n"
        f"Applicant needs (Q2): {main_needs or '(not provided)'}\n"
        f"Software wanted (Q3): {software or '(none specified)'}\n"
        f"Challenge without a computer (Q4): {challenge or '(not provided)'}\n\n"
        "Score each candidate below and explain, citing source filenames. Return JSON "
        '{"assessments": [{"device_id","needs_fit","challenge_fit","explanation","citations"}]} '
        "with exactly one entry per device, using the device_id shown.\n\n"
        + "\n".join(blocks)
    )

    try:
        raw = (generate_fn or _generate)(_FIT_SYSTEM, user, temperature=0.2, response_schema=_FIT_SCHEMA)
        parsed = _parse_json(raw) or {}
        by_id: dict[str, dict[str, Any]] = {}
        for entry in parsed.get("assessments", []) or []:
            did = str(entry.get("device_id", "")).strip()
            if did:
                by_id[did] = {
                    "needs_fit": _clamp01(entry.get("needs_fit")),
                    "challenge_fit": _clamp01(entry.get("challenge_fit")),
                    "explanation": str(entry.get("explanation", "")).strip(),
                    "citations": list(entry.get("citations") or []),
                }
        if not by_id:
            raise ValueError("no assessments parsed from model output")
        fb, _ = _fallback()
        for d in devices:
            by_id.setdefault(d.id, fb[d.id])
        return by_id, True
    except Exception as exc:
        _note_fallback()
        _log.warning("· fit_and_explain: fell back to neutral scores (%s)", short(exc))
        _audit({"task": "fit_and_explain_fallback", "error": str(exc)})
        return _fallback()

