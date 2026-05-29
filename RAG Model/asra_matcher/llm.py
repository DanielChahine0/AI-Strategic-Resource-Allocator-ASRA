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

from pydantic import BaseModel

from . import cache, ratelimit
from .models import (
    Application,
    Device,
    IntakeAnswers,
    RagContext,
    RetrievedChunk,
)
from .rag import prompts
from .rag import retrieve as retrieve_mod
from .taxonomy import Category, DeviceTier

DEFAULT_GEN_MODEL = "gemini-2.5-flash-lite"
TEMP_PARSE = 0.1
TEMP_TIER = 0.1
TEMP_EXPLAIN = 0.4


def _max_output_tokens() -> int:
    """Cap output to avoid runaway generations. Generous enough not to truncate
    the small JSON payloads these tasks emit."""
    try:
        return int(os.environ.get("ASRA_MAX_OUTPUT_TOKENS", "1024"))
    except ValueError:
        return 1024


def _model() -> str:
    return os.environ.get("ASRA_GENERATION_MODEL", DEFAULT_GEN_MODEL)


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
    """Begin capturing token usage for the current context. Returns the ledger."""
    ledger = {"input": 0, "output": 0, "total": 0, "calls": 0}
    _TOKEN_LEDGER.set(ledger)
    return ledger


def read_token_capture() -> dict | None:
    """Return the active ledger (or None if capture was never started)."""
    return _TOKEN_LEDGER.get()


def stop_token_capture() -> None:
    _TOKEN_LEDGER.set(None)


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


@dataclass
class TierRecommendation:
    recommended_tier: DeviceTier
    rationale: str
    citations: list[str]
    confidence: float
    abstained: bool = False
    fallback_used: bool = False
    chunks: list[RetrievedChunk] = None  # type: ignore[assignment]


@dataclass
class MatchExplanation:
    explanations: dict[str, str]   # device_id -> explanation
    citations: dict[str, list[str]]  # device_id -> [source_path,...]
    fallback_used: bool = False
    chunks: list[RetrievedChunk] = None  # type: ignore[assignment]


@dataclass
class IntakeParseResult:
    parsed: IntakeAnswers
    citations: list[str]
    uncertain_fields: list[str]
    fallback_used: bool = False
    chunks: list[RetrievedChunk] = None  # type: ignore[assignment]


class _IntakeParseEnvelope(BaseModel):
    """Native response_schema for parse_intake — lets Gemini emit the parsed
    object plus citations/uncertain_fields in a constrained shape, so the full
    IntakeAnswers JSON-schema no longer has to be inlined into the prompt."""

    parsed: IntakeAnswers
    citations: list[str] = []
    uncertain_fields: list[str] = []


# ---------------------------------------------------------------------------
# Low-level generation
# ---------------------------------------------------------------------------


def _client():
    from google import genai  # type: ignore

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


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
    key = bool(os.environ.get("GEMINI_API_KEY"))
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
        return hit

    last_exc: Exception | None = None
    for _attempt in range(2):
        try:
            client = _client()
            cfg_kwargs: dict[str, Any] = {
                "temperature": temperature,
                "system_instruction": system,
                "max_output_tokens": _max_output_tokens(),
            }
            if json_mode:
                cfg_kwargs["response_mime_type"] = "application/json"
            if response_schema is not None:
                cfg_kwargs["response_schema"] = response_schema
            cfg = types.GenerateContentConfig(**cfg_kwargs)
            ratelimit.wait_generation()
            resp = client.models.generate_content(
                model=_model(), contents=user, config=cfg
            )
            _record_usage(resp)
            _record_success()
            text = resp.text or ""
            cache.put("gen", ck, text)
            return text
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5)
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
# Task A — tier recommendation
# ---------------------------------------------------------------------------


def recommend_tier(
    application: Application,
    *,
    retrieve_fn=None,
    generate_fn=None,
    today: datetime | None = None,
) -> TierRecommendation:
    """RAG-augmented tier recommendation for A3 / C applications."""
    retrieve_fn = retrieve_fn or retrieve_mod.query
    cat_filter = {"category": application.category.value}
    chunks = []
    try:
        chunks += retrieve_fn(
            application.intake.main_usage + " " + " ".join(application.intake.software_needed),
            namespaces=["categories"],
            k_per_namespace=4,
            filters={"categories": cat_filter},
        )
        chunks += retrieve_fn(
            application.intake.main_usage,
            namespaces=["tiers"],
            k_per_namespace=3,
        )
        if application.intake.software_needed:
            chunks += retrieve_fn(
                " ".join(application.intake.software_needed),
                namespaces=["software"],
                k_per_namespace=4,
            )
        chunks += retrieve_fn(
            application.intake.main_usage,
            namespaces=["decisions"],
            k_per_namespace=2,
            filters={"decisions": cat_filter},
        )
    except Exception:
        # Retrieval failure: pipeline continues with empty context → triggers fallback.
        chunks = []

    chunks = _prune_chunks(chunks)
    ctx = RagContext(task="tier_recommendation", chunks=chunks)
    system, user = prompts.tier_recommendation_prompt(application, ctx)

    raw = ""
    parsed: dict[str, Any] | None = None
    error: str | None = None
    fallback_used = False
    try:
        gen = generate_fn or _generate
        raw = gen(system, user, temperature=TEMP_TIER)
        parsed = _parse_json(raw)
    except Exception as exc:
        error = repr(exc)
        parsed = None

    abstained = bool(parsed and parsed.get("abstain"))
    if parsed and not abstained and parsed.get("recommended_tier") in {"T1", "T2", "T3"}:
        rec = TierRecommendation(
            recommended_tier=DeviceTier(parsed["recommended_tier"]),
            rationale=parsed.get("rationale", ""),
            citations=list(parsed.get("citations") or []),
            confidence=float(parsed.get("confidence") or 0.0),
            chunks=chunks,
        )
    else:
        fallback_used = True
        rec = TierRecommendation(
            recommended_tier=_conservative_fallback_tier(application),
            rationale="LLM abstained or failed; using conservative fallback tier.",
            citations=[],
            confidence=0.0,
            abstained=abstained,
            fallback_used=True,
            chunks=chunks,
        )

    _audit(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "task": "recommend_tier",
            "applicant_id": application.applicant_id,
            "category": application.category.value,
            "retrieved_chunks": [
                {"source_path": c.source_path, "similarity": c.similarity}
                for c in chunks
            ],
            "raw_response": raw,
            "error": error,
            "fallback_used": fallback_used,
            "result": {
                "recommended_tier": rec.recommended_tier.value,
                "confidence": rec.confidence,
            },
        }
    )
    return rec


def _conservative_fallback_tier(app: Application) -> DeviceTier:
    """When the LLM abstains, pick the most conservative tier."""
    if app.category == Category.A3:
        if app.intake.a3_subtrack and app.intake.a3_subtrack.value == "software_engineering":
            # Default to Standard unless software signals otherwise.
            return DeviceTier.T2
        return DeviceTier.T2
    if app.category == Category.C:
        return DeviceTier.T3
    return DeviceTier.T3


# ---------------------------------------------------------------------------
# Task B — match explanations
# ---------------------------------------------------------------------------


def explain_matches(
    application: Application,
    devices: list[Device],
    *,
    retrieve_fn=None,
    generate_fn=None,
) -> MatchExplanation:
    retrieve_fn = retrieve_fn or retrieve_mod.query
    chunks: list[RetrievedChunk] = []
    try:
        chunks += retrieve_fn(
            application.intake.main_usage,
            namespaces=["decisions"],
            k_per_namespace=3,
            filters={"decisions": {"category": application.category.value}},
        )
        chunks += retrieve_fn(
            "scoring weights priority timing condition efficiency multi-category",
            namespaces=["policies"],
            k_per_namespace=2,
        )
        tiers_present = {d.tier.value for d in devices if d.tier}
        if tiers_present:
            chunks += retrieve_fn(
                "tier definitions " + " ".join(tiers_present),
                namespaces=["tiers"],
                k_per_namespace=2,
            )
    except Exception:
        chunks = []

    chunks = _prune_chunks(chunks)
    ctx = RagContext(task="explain_matches", chunks=chunks)
    system, user = prompts.explanation_prompt(application, devices, ctx)

    raw = ""
    parsed: dict[str, Any] | None = None
    error: str | None = None
    fallback_used = False
    try:
        gen = generate_fn or _generate
        raw = gen(system, user, temperature=TEMP_EXPLAIN)
        parsed = _parse_json(raw)
    except Exception as exc:
        error = repr(exc)

    explanations: dict[str, str] = {}
    citations: dict[str, list[str]] = {}
    if parsed and not parsed.get("abstain"):
        for entry in parsed.get("explanations") or []:
            did = entry.get("device_id")
            if not did:
                continue
            explanations[did] = entry.get("explanation", "")
            citations[did] = list(entry.get("citations") or [])
    if not explanations:
        fallback_used = True
        for d in devices:
            explanations[d.id] = (
                f"Device {d.id} ({d.item_type.value}, "
                f"tier {d.tier.value if d.tier else 'n/a'}, condition {d.condition}/5) "
                f"is the highest-scoring fit for this {application.category.value} application "
                "based on the deterministic score breakdown."
            )
            citations[d.id] = []

    _audit(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "task": "explain_matches",
            "applicant_id": application.applicant_id,
            "category": application.category.value,
            "device_ids": [d.id for d in devices],
            "retrieved_chunks": [
                {"source_path": c.source_path, "similarity": c.similarity}
                for c in chunks
            ],
            "raw_response": raw,
            "error": error,
            "fallback_used": fallback_used,
        }
    )
    return MatchExplanation(
        explanations=explanations,
        citations=citations,
        fallback_used=fallback_used,
        chunks=chunks,
    )


# ---------------------------------------------------------------------------
# Task C — intake parse
# ---------------------------------------------------------------------------


def parse_intake(
    raw_answers: dict[str, Any],
    *,
    retrieve_fn=None,
    generate_fn=None,
    applicant_id: str = "unknown",
) -> IntakeParseResult:
    retrieve_fn = retrieve_fn or retrieve_mod.query
    purpose_hint = str(raw_answers.get("q2", ""))
    sw_hint = str(raw_answers.get("q4", ""))

    chunks: list[RetrievedChunk] = []
    try:
        chunks += retrieve_fn(
            purpose_hint or raw_answers.get("q3", ""),
            namespaces=["categories"],
            k_per_namespace=3,
        )
        if sw_hint and sw_hint.lower() not in {"none", ""}:
            chunks += retrieve_fn(
                sw_hint, namespaces=["software"], k_per_namespace=3
            )
    except Exception:
        chunks = []

    chunks = _prune_chunks(chunks)
    ctx = RagContext(task="parse_intake", chunks=chunks)
    system, user = prompts.intake_parse_prompt(raw_answers, ctx)

    raw = ""
    parsed_json: dict[str, Any] | None = None
    error: str | None = None
    fallback_used = False
    try:
        gen = generate_fn or _generate
        if generate_fn is None:
            # Native structured output: Gemini returns {parsed, citations,
            # uncertain_fields} matching _IntakeParseEnvelope, so the full
            # IntakeAnswers JSON-schema no longer has to be inlined into the
            # prompt (it was ~424 tokens re-sent on every call).
            raw = gen(
                system, user, temperature=TEMP_PARSE,
                response_schema=_IntakeParseEnvelope,
            )
        else:
            raw = gen(system, user, temperature=TEMP_PARSE)
        parsed_json = _parse_json(raw)
    except Exception as exc:
        error = repr(exc)

    citations: list[str] = []
    uncertain: list[str] = []
    intake_obj: IntakeAnswers | None = None
    if parsed_json and not parsed_json.get("abstain"):
        try:
            intake_obj = IntakeAnswers.model_validate(parsed_json.get("parsed") or parsed_json)
            citations = list(parsed_json.get("citations") or [])
            uncertain = list(parsed_json.get("uncertain_fields") or [])
        except Exception as exc:
            error = (error or "") + f" | validation: {exc!r}"

    if intake_obj is None:
        # Deterministic fallback: best-effort heuristic parser using raw answers.
        fallback_used = True
        intake_obj = _heuristic_parse(raw_answers)

    _audit(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "task": "parse_intake",
            "applicant_id": applicant_id,
            "retrieved_chunks": [
                {"source_path": c.source_path, "similarity": c.similarity}
                for c in chunks
            ],
            "raw_response": raw,
            "error": error,
            "fallback_used": fallback_used,
        }
    )
    return IntakeParseResult(
        parsed=intake_obj,
        citations=citations,
        uncertain_fields=uncertain,
        fallback_used=fallback_used,
        chunks=chunks,
    )


# ---------------------------------------------------------------------------
# Heuristic fallback for parse_intake
# ---------------------------------------------------------------------------

_PURPOSE_KEYWORDS = {
    "school": Category.A2,
    "learning": Category.A2,
    "k-6": Category.A1,
    "elementary": Category.A1,
    "high school": Category.A2,
    "post-secondary": Category.A3,
    "university": Category.A3,
    "college": Category.A3,
    "work": Category.C,
    "job": Category.C,
    "employment": Category.C,
    "healthcare": Category.B,
    "medical": Category.B,
    "personal": Category.E,
    "browsing": Category.E,
    "newcomer": Category.F,
    "immigrant": Category.F,
    "canada": Category.F,
    "senior": Category.D,
    "elder": Category.D,
}

_URGENCY_KEYWORDS = {
    "this week": "critical",
    "critical": "critical",
    "urgent": "critical",
    "month": "high",
    "soon": "high",
    "1-3": "medium",
    "couple months": "medium",
    "medium": "medium",
    "flexible": "low",
    "no rush": "low",
    "low": "low",
}


def _heuristic_parse(raw: dict[str, Any]) -> IntakeAnswers:
    text_all = " ".join(str(v) for v in raw.values()).lower()
    purposes: list[Category] = []
    for kw, cat in _PURPOSE_KEYWORDS.items():
        if kw in text_all and cat not in purposes:
            purposes.append(cat)
    if not purposes:
        purposes = [Category.E]  # personal browsing default

    urgency = "medium"
    for kw, u in _URGENCY_KEYWORDS.items():
        if kw in text_all:
            urgency = u
            break

    sw_raw = str(raw.get("q4", "")).strip()
    software_list: list[str] = []
    if sw_raw and sw_raw.lower() != "none":
        software_list = [s.strip() for s in re.split(r"[,;]", sw_raw) if s.strip()]

    shared = 1
    m = re.search(r"\b(\d+)\b", str(raw.get("q5", "")))
    if m:
        try:
            shared = max(1, int(m.group(1)))
        except ValueError:
            shared = 1

    return IntakeAnswers(
        who_needs_it=str(raw.get("q1", "")).strip() or "unspecified",
        purpose=purposes,
        a3_subtrack=None,
        main_usage=str(raw.get("q3", "")).strip() or "general use",
        software_needed=software_list,
        shared_user_count=shared,
        urgency=urgency,  # type: ignore[arg-type]
        current_tech_access={"has_internet": None, "device_situation": None, "notes": str(raw.get("q7", ""))},
    )
