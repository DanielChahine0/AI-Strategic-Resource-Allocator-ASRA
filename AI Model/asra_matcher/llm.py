"""Gemini 2.5 Flash Lite wrapper.

The LLM handles only three narrow tasks:
  A. `recommend_tier`   — pick a tier for non-deterministic categories (A3, C)
  B. `explain_matches`  — write a 2–3 sentence human-readable rationale per match
  C. `parse_intake`     — turn raw free-text answers into a structured IntakeAnswers

All other logic is deterministic. Every LLM failure falls back to a sane
default so the engine never crashes on the LLM.

The wrapper writes every prompt + response to ./logs/llm_audit.jsonl.
Environment variable `GEMINI_API_KEY` is required for live calls; if unset,
`is_available()` returns False and callers should use the deterministic
fallback paths.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv()
except Exception:  # pragma: no cover — dotenv is optional at runtime
    pass

# google-genai is optional at import time so tests can run without network.
try:
    from google import genai  # type: ignore
    from google.genai import types as genai_types  # type: ignore

    _GENAI_IMPORT_OK = True
except Exception:  # pragma: no cover
    genai = None  # type: ignore
    genai_types = None  # type: ignore
    _GENAI_IMPORT_OK = False


from asra_matcher import cache, ratelimit

MODEL_ID = "gemini-2.5-flash-lite"
TEMPERATURE = 0.2
AUDIT_LOG = Path("logs/llm_audit.jsonl")

# Real-time console logger (stderr). Separate from the JSONL audit log above:
# this one narrates each Gemini call live so `./run.sh` shows *why* the engine
# is or isn't using the LLM. See asra_matcher/obslog.py.
from asra_matcher.obslog import get_logger, short

_log = get_logger("ai")

# Tracks the rate-limit window we last shouted about, so the big "quota
# exhausted" banner prints once per window instead of once per failed call.
_quota_banner_until: float | None = None


def _max_output_tokens() -> int:
    """Cap output to avoid runaway generations. Generous enough not to truncate
    the small JSON/text payloads these tasks emit."""
    try:
        return int(os.environ.get("ASRA_MAX_OUTPUT_TOKENS", "1024"))
    except ValueError:
        return 1024


def _thinking_budget() -> int:
    """Token budget for model 'thinking'. 0 disables it (the default for these
    narrow extraction/classification tasks; thinking tokens bill at the 4x
    output rate). Override via ASRA_THINKING_BUDGET."""
    try:
        return int(os.environ.get("ASRA_THINKING_BUDGET", "0"))
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Token capture (used by the evaluation harness — see asra_matcher.eval)
# ---------------------------------------------------------------------------
#
# The eval runner wraps a single `engine.match()` call in start/read so it can
# attribute Gemini token usage to one applicant. This is opt-in: when no ledger
# is active (the normal /match path), `_record_usage` is a no-op, so production
# behaviour is unchanged.

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
# Client + audit log
# ---------------------------------------------------------------------------


# One genai.Client per API key, built on demand. The KeyPool decides which key
# to use and parks any that hit a 429 / auth error (see asra_matcher.keypool).
_clients: dict[str, Any] = {}
_keypool: Any | None = None


def _pool():
    """Lazily build the process-wide KeyPool from the environment."""
    global _keypool
    if _keypool is None:
        from asra_matcher import keypool as _kp

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
    """Return (and cache) a genai.Client bound to a specific key."""
    c = _clients.get(key)
    if c is None:
        if not _GENAI_IMPORT_OK:
            raise RuntimeError("google-genai SDK not installed")
        c = genai.Client(api_key=key)  # type: ignore
        _clients[key] = c
        _log.info("Gemini client ready — model=%s key=…%s", MODEL_ID, key[-4:])
    return c


def _retry_seconds(msg: str) -> float:
    """Seconds to park a key after a 429, parsed from the error (default 60s)."""
    m = _RETRY_RE.search(msg) or _RETRY_RE2.search(msg)
    return float(m.group(1)) if m else 60.0


def _audit(record: dict[str, Any]) -> None:
    """Append one JSONL line to the audit log. Never raises."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": datetime.now(UTC).isoformat(), **record}
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


def is_available() -> bool:
    """Cheap check used by callers to decide between LLM and fallback paths."""
    return _GENAI_IMPORT_OK and _pool().has_keys()


# ---------------------------------------------------------------------------
# Live model health (surfaced via the API /status endpoint)
# ---------------------------------------------------------------------------
#
# We record the outcome of every real Gemini call into a process-local state
# dict rather than probing the model on each status request — a probe would
# itself consume the (very small) free-tier quota we are trying to protect.
# This makes the engine's *actual* behaviour observable: whether it is serving
# live LLM output or quietly running on deterministic fallbacks.

import re as _re

_HEALTH: dict[str, Any] = {
    "total_calls": 0,
    "total_success": 0,
    "total_failures": 0,
    "consecutive_failures": 0,
    "last_call_ts": None,       # epoch seconds
    "last_success_ts": None,    # epoch seconds
    "last_error": None,         # str (truncated)
    "last_error_kind": None,    # "rate_limit" | "auth" | "other"
    "rate_limited_until": None,  # epoch seconds the 429 retryDelay expires
    "quota": None,              # {"limit", "quota_id", "metric"} parsed from a 429
}

_RETRY_RE = _re.compile(r"retry in ([\d.]+)s", _re.IGNORECASE)
_RETRY_RE2 = _re.compile(r"retryDelay'?:?\s*'?(\d+(?:\.\d+)?)s", _re.IGNORECASE)
_LIMIT_RE = _re.compile(r"limit:\s*(\d+)")
_QUOTA_ID_RE = _re.compile(r"quotaId'?:?\s*'?([A-Za-z0-9\-]+)")
_METRIC_RE = _re.compile(r"quotaMetric'?:?\s*'?([A-Za-z0-9_./\-]+)")

# Short, plain-English note shown in the dashboard for each state.
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
                MODEL_ID,
                int(secs) if secs else "?",
            )
    elif kind == "auth":
        _log.error(
            "🔑 GEMINI AUTH ERROR — key rejected. Check GEMINI_API_KEY in 'AI Model/.env'. %s",
            short(msg),
        )
    else:
        _log.error("⚠ GEMINI CALL ERROR [other] — %s", short(msg))


def _iso(ts: float | None) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, UTC).isoformat()


def model_status(probe: bool = False) -> dict[str, Any]:
    """Return a structured snapshot of the generation model's live state.

    By default this is derived purely from the outcomes of real calls made
    this session (zero quota cost). Pass ``probe=True`` to spend one cheap
    Gemini call confirming the model answers right now.
    """
    sdk = _GENAI_IMPORT_OK
    key = _pool().has_keys()
    now = time.time()

    rlu = _HEALTH["rate_limited_until"]
    rate_limited = bool(rlu and rlu > now)

    if probe and sdk and key and not rate_limited:
        try:
            _generate_text("Reply with the single word: OK")
        except Exception:
            pass  # outcome is recorded in _HEALTH by the call itself
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
        "model": MODEL_ID,
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


def _build_config(system: str | None, schema: Any | None, *, json_mode: bool):
    config_kwargs: dict[str, Any] = {
        "temperature": TEMPERATURE,
        "max_output_tokens": _max_output_tokens(),
    }
    if json_mode:
        config_kwargs["response_mime_type"] = "application/json"
    if system:
        config_kwargs["system_instruction"] = system
    if schema is not None:
        config_kwargs["response_schema"] = schema
    config_kwargs["thinking_config"] = genai_types.ThinkingConfig(  # type: ignore
        thinking_budget=_thinking_budget()
    )
    return genai_types.GenerateContentConfig(**config_kwargs)  # type: ignore


def _generate_raw(prompt: str, system: str | None, schema: Any | None, *, json_mode: bool) -> str:
    """One Gemini generation, rotating across the key pool.

    Tries live keys in round-robin order; a key that returns 429 is parked for
    its retry window and the next key is tried, so multiple free-tier keys
    multiply the effective quota. Transient errors get one same-key retry.
    Raises when every key is exhausted/failed so callers fall back.
    """
    pool = _pool()
    config = _build_config(system, schema, json_mode=json_mode)
    last_err: Exception | None = None
    # Give each key a shot, plus one extra for a transient single-key retry.
    max_tries = max(2, len(pool) + 1)
    transient_retry_used = False

    for _ in range(max_tries):
        key = pool.acquire()
        if key is None:
            last_err = last_err or RuntimeError("all Gemini API keys are cooling (rate-limited)")
            break
        try:
            ratelimit.wait_generation()
            response = _client_for(key).models.generate_content(
                model=MODEL_ID, contents=prompt, config=config
            )
            _record_usage(response)
            text = (response.text or "").strip()
            _record_success()
            um = getattr(response, "usage_metadata", None)
            _log.info(
                "✓ Gemini OK key=…%s — tokens in=%s out=%s total=%s",
                key[-4:],
                getattr(um, "prompt_token_count", "?"),
                getattr(um, "candidates_token_count", "?"),
                getattr(um, "total_token_count", "?"),
            )
            return text
        except Exception as exc:
            last_err = exc
            kind = _classify_error(str(exc))
            if kind == "rate_limit":
                secs = _retry_seconds(str(exc))
                pool.mark_cooling(key, secs)
                _log.warning(
                    "✗ key …%s rate-limited (429) — cooling %ss, rotating", key[-4:], int(secs)
                )
                continue
            if kind == "auth":
                pool.mark_cooling(key, 3600)
                _log.warning("✗ key …%s rejected (auth) — disabling 1h, rotating", key[-4:])
                continue
            if not transient_retry_used:
                transient_retry_used = True
                _log.warning("✗ Gemini failed [%s] — retrying once: %s", kind, short(exc))
                time.sleep(0.3)
                continue
            break

    _record_failure(last_err)  # type: ignore[arg-type]
    raise last_err  # type: ignore[misc]


def _generate_json(prompt: str, system: str | None = None, schema: Any | None = None) -> dict:
    """Call Gemini with a structured-JSON output instruction (key-pool aware).

    Cached by content hash; raises on hard failure so callers fall back.
    """
    ck = cache.make_key("json", MODEL_ID, TEMPERATURE, prompt, system, schema)
    hit = cache.get("gen", ck)
    if hit is not None:
        _note_cache_hit()
        _log.debug("✓ cache hit (json) — served from disk, no API call, 0 tokens")
        return hit

    _log.debug("→ Gemini json call — prompt=%d chars, schema=%s", len(prompt), schema is not None)
    try:
        text = _generate_raw(prompt, system, schema, json_mode=True)
        data = json.loads(text)
    except Exception as exc:
        _audit({"task": "json_call_failed", "error": str(exc), "prompt": prompt[:2000]})
        raise
    cache.put("gen", ck, data)
    _audit({
        "task": "json_call",
        "prompt": prompt[:2000],
        "system": (system or "")[:500],
        "response": text[:2000],
    })
    return data


def _generate_text(prompt: str, system: str | None = None) -> str:
    """Call Gemini and return raw text (key-pool aware)."""
    ck = cache.make_key("text", MODEL_ID, TEMPERATURE, prompt, system)
    hit = cache.get("gen", ck)
    if hit is not None:
        _note_cache_hit()
        _log.debug("✓ cache hit (text) — served from disk, no API call, 0 tokens")
        return hit

    _log.debug("→ Gemini text call — prompt=%d chars", len(prompt))
    text = _generate_raw(prompt, system, None, json_mode=False)
    cache.put("gen", ck, text)
    _audit({"task": "text_call", "prompt": prompt[:2000], "response": text[:2000]})
    return text



# ---------------------------------------------------------------------------
# Simplified flow — single combined "fit + explain" call (Q1–Q4 model)
# ---------------------------------------------------------------------------
#
# The simplified allocator (asra_matcher.simple) sends ONE call per applicant:
# given the applicant's free-text needs (Q2), software (Q3), and challenge (Q4),
# score how well each pre-filtered candidate device fits and write a short
# rationale. Q1 (OS) and the software-capability check are deterministic and
# never reach the model, so this is the only token spend in the new pipeline.

_FIT_SYSTEM = (
    "You help a nonprofit match donated, refurbished computers to applicants. "
    "For EACH candidate device, judge how well it serves the applicant's stated "
    "needs and how much it addresses the difficulties they face without a "
    "computer. Return two scores in [0,1] — needs_fit (match to their described "
    "use) and challenge_fit (how well it relieves their stated challenge) — plus "
    "a concrete 1–2 sentence rationale that cites their own words and the "
    "device's specs. Do not invent specs. Higher-condition, adequately-powered "
    "machines should score higher for demanding needs; a modest machine is fine "
    "for light needs."
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


def _fit_prompt(main_needs: str, software: str, challenge: str, devices: list[Any]) -> str:
    blocks: list[str] = []
    for d in devices:
        tier = d.tier.value if getattr(d, "tier", None) else "n/a"
        blocks.append(
            f"--- Device {d.id} ---\n"
            f"tier: {tier}, condition: {d.condition}/5\n"
            f"specs: {d.specs}"
        )
    return (
        f"Applicant needs (Q2): {main_needs or '(not provided)'}\n"
        f"Software wanted (Q3): {software or '(none specified)'}\n"
        f"Challenge without a computer (Q4): {challenge or '(not provided)'}\n\n"
        "Score each candidate below and explain. Return JSON "
        '{"assessments": [{"device_id", "needs_fit", "challenge_fit", "explanation"}]} '
        "with exactly one entry per device, using the device_id shown.\n\n"
        + "\n".join(blocks)
    )


def fit_and_explain(
    main_needs: str,
    software: str,
    challenge: str,
    devices: list[Any],
) -> tuple[dict[str, dict[str, Any]], bool]:
    """Score + explain a small candidate set in one call.

    Returns ``(by_device_id, used_ai)`` where each value is
    ``{"needs_fit": float, "challenge_fit": float, "explanation": str}``.
    On any failure (or no key/SDK) returns neutral 0.6 scores with a
    deterministic template and ``used_ai=False`` so the engine still ranks.
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
            }
        return out, False

    if not is_available():
        _note_fallback()
        _log.info("· fit_and_explain: LLM unavailable → neutral scores for %d device(s)", len(devices))
        return _fallback()

    try:
        data = _generate_json(
            _fit_prompt(main_needs, software, challenge, devices),
            system=_FIT_SYSTEM,
            schema=_FIT_SCHEMA,
        )
        by_id: dict[str, dict[str, Any]] = {}
        for entry in data.get("assessments", []) or []:
            did = str(entry.get("device_id", "")).strip()
            if did:
                by_id[did] = {
                    "needs_fit": _clamp01(entry.get("needs_fit")),
                    "challenge_fit": _clamp01(entry.get("challenge_fit")),
                    "explanation": str(entry.get("explanation", "")).strip(),
                }
        # Fill any device the model omitted with a neutral entry.
        fb, _ = _fallback()
        for d in devices:
            by_id.setdefault(d.id, fb[d.id])
        return by_id, True
    except Exception as exc:
        _note_fallback()
        _log.warning("· fit_and_explain: fell back to neutral scores (%s)", short(exc))
        _audit({"task": "fit_and_explain_fallback", "error": str(exc)})
        return _fallback()
