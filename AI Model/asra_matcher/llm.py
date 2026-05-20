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
from datetime import datetime, timezone
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


from asra_matcher.models import Application, Device, IntakeAnswers, MatchResult
from asra_matcher.taxonomy import DeviceTier

MODEL_ID = "gemini-2.5-flash-lite"
TEMPERATURE = 0.2
AUDIT_LOG = Path("logs/llm_audit.jsonl")


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


# ---------------------------------------------------------------------------
# Client + audit log
# ---------------------------------------------------------------------------


_client: Any | None = None


def _audit(record: dict[str, Any]) -> None:
    """Append one JSONL line to the audit log. Never raises."""
    try:
        AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": datetime.now(timezone.utc).isoformat(), **record}
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception:
        pass


def is_available() -> bool:
    """Cheap check used by callers to decide between LLM and fallback paths."""
    return _GENAI_IMPORT_OK and bool(os.getenv("GEMINI_API_KEY"))


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

# Human-readable explanation per derived state.
_STATE_DETAIL = {
    "live": "Serving live Gemini output.",
    "ready": "Configured and ready; no calls made yet this session.",
    "rate_limited": "Gemini quota exhausted (HTTP 429). Running deterministic "
    "fallbacks until the quota window resets.",
    "auth_error": "Gemini rejected the API key. Check GEMINI_API_KEY.",
    "no_api_key": "GEMINI_API_KEY is not set; running deterministic fallbacks.",
    "sdk_missing": "google-genai SDK is not installed; running deterministic fallbacks.",
    "degraded": "Recent Gemini calls are failing; serving deterministic fallbacks.",
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
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def model_status(probe: bool = False) -> dict[str, Any]:
    """Return a structured snapshot of the generation model's live state.

    By default this is derived purely from the outcomes of real calls made
    this session (zero quota cost). Pass ``probe=True`` to spend one cheap
    Gemini call confirming the model answers right now.
    """
    sdk = _GENAI_IMPORT_OK
    key = bool(os.getenv("GEMINI_API_KEY"))
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


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not _GENAI_IMPORT_OK:
        raise RuntimeError("google-genai SDK not installed")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    _client = genai.Client(api_key=api_key)  # type: ignore
    return _client


def _generate_json(prompt: str, system: str | None = None, schema: dict | None = None) -> dict:
    """Call Gemini with a structured-JSON output instruction.

    Retries once on transient failure. Raises on hard failure so callers can
    fall back deterministically.
    """
    client = _get_client()

    config_kwargs: dict[str, Any] = {
        "temperature": TEMPERATURE,
        "response_mime_type": "application/json",
    }
    if system:
        config_kwargs["system_instruction"] = system
    if schema is not None:
        config_kwargs["response_schema"] = schema
    config = genai_types.GenerateContentConfig(**config_kwargs)  # type: ignore

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=config,
            )
            _record_usage(response)
            text = (response.text or "").strip()
            data = json.loads(text)
            _record_success()
            _audit({
                "task": "json_call",
                "attempt": attempt,
                "prompt": prompt[:2000],
                "system": (system or "")[:500],
                "response": text[:2000],
            })
            return data
        except Exception as exc:
            last_err = exc
            time.sleep(0.3)
    _record_failure(last_err)  # type: ignore[arg-type]
    _audit({"task": "json_call_failed", "error": str(last_err), "prompt": prompt[:2000]})
    raise last_err  # type: ignore[misc]


def _generate_text(prompt: str, system: str | None = None) -> str:
    """Call Gemini and return raw text. One retry."""
    client = _get_client()
    config_kwargs: dict[str, Any] = {"temperature": TEMPERATURE}
    if system:
        config_kwargs["system_instruction"] = system
    config = genai_types.GenerateContentConfig(**config_kwargs)  # type: ignore

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL_ID,
                contents=prompt,
                config=config,
            )
            _record_usage(response)
            text = (response.text or "").strip()
            _record_success()
            _audit({
                "task": "text_call",
                "attempt": attempt,
                "prompt": prompt[:2000],
                "response": text[:2000],
            })
            return text
        except Exception as exc:
            last_err = exc
            time.sleep(0.3)
    _record_failure(last_err)  # type: ignore[arg-type]
    _audit({"task": "text_call_failed", "error": str(last_err)})
    raise last_err  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task A — Tier recommendation
# ---------------------------------------------------------------------------


_TIER_SYSTEM = (
    "You are a hardware-allocation assistant for a nonprofit that gives "
    "donated computers to people in need. Recommend the appropriate device "
    "tier given the applicant's stated needs.\n\n"
    "Tier definitions:\n"
    "- T1 High Power: video editing, ML training, VMs, heavy IDEs, Android/iOS emulators.\n"
    "- T2 Standard: university coursework, office work, light creative.\n"
    "- T3 Basic: browsing, email, documents, video calls, government services.\n\n"
    "Be conservative — only recommend higher tiers when the stated software "
    "or workload genuinely requires it.\n"
    "Output JSON: {\"recommended_tier\": \"T1|T2|T3\", \"rationale\": \"...\", \"confidence\": 0-1}."
)


def recommend_tier(application: Application, candidate_tiers: set[DeviceTier]) -> dict[str, Any]:
    """Ask Gemini to narrow a candidate set. Returns dict with keys
    `recommended_tier` (DeviceTier), `rationale` (str), `confidence` (float).

    On any failure, falls back to:
      - T2 if T2 is in the candidate set
      - else the *lowest* tier available (most conservative)
    """
    if not is_available():
        return _tier_fallback(candidate_tiers, reason="LLM unavailable; deterministic fallback")

    intake = application.intake
    candidate_list = sorted(t.value for t in candidate_tiers)
    prompt = (
        f"Applicant category: {application.category.value}\n"
        f"A3 sub-track: {intake.a3_subtrack.value if intake.a3_subtrack else 'n/a'}\n"
        f"Program: {intake.program_name or 'n/a'}\n"
        f"Main usage: {intake.main_usage}\n"
        f"Software required: {intake.software_needed}\n"
        f"Shared users: {intake.shared_user_count}\n"
        f"Urgency: {intake.urgency.value}\n"
        f"Candidate tiers (must pick one of these): {candidate_list}\n"
        "Respond with strict JSON only."
    )

    try:
        data = _generate_json(prompt, system=_TIER_SYSTEM)
        raw = str(data.get("recommended_tier", "")).upper()
        if raw not in candidate_list:
            return _tier_fallback(candidate_tiers, reason=f"LLM returned {raw}; out of set")
        return {
            "recommended_tier": DeviceTier(raw),
            "rationale": str(data.get("rationale", "")),
            "confidence": float(data.get("confidence", 0.5)),
        }
    except Exception as exc:
        _audit({"task": "recommend_tier_fallback", "error": str(exc)})
        return _tier_fallback(candidate_tiers, reason=f"LLM error: {exc}")


def _tier_fallback(candidate_tiers: set[DeviceTier], reason: str) -> dict[str, Any]:
    if DeviceTier.T2 in candidate_tiers:
        chosen = DeviceTier.T2
    elif DeviceTier.T3 in candidate_tiers:
        chosen = DeviceTier.T3
    elif DeviceTier.T1 in candidate_tiers:
        chosen = DeviceTier.T1
    else:
        chosen = DeviceTier.T3
    return {
        "recommended_tier": chosen,
        "rationale": f"Deterministic fallback ({reason}); chose conservative tier.",
        "confidence": 0.0,
    }


# ---------------------------------------------------------------------------
# Task B — Explanations for the top-2 matches
# ---------------------------------------------------------------------------


_EXPLAIN_SYSTEM = (
    "You are summarising why a specific donated device is a good match for "
    "a specific applicant, for the human reviewer who will approve the "
    "allocation. Write 2 to 3 sentences. Be concrete: cite the device tier, "
    "the applicant's stated need, and any noteworthy score (timing, condition, "
    "priority). Do not invent facts. Do not rank or compare against other "
    "devices. Do not change the recommendation."
)


def explain_matches(application: Application, matches: list[MatchResult]) -> list[str]:
    """Return a 2-3 sentence rationale per match. Same length as `matches`."""
    if not matches:
        return []

    if not is_available():
        return [_explain_fallback(application, m) for m in matches]

    explanations: list[str] = []
    for m in matches:
        prompt = _explain_prompt(application, m)
        try:
            text = _generate_text(prompt, system=_EXPLAIN_SYSTEM)
            explanations.append(text)
        except Exception as exc:
            _audit({"task": "explain_fallback", "error": str(exc)})
            explanations.append(_explain_fallback(application, m))
    return explanations


def _explain_prompt(application: Application, match: MatchResult) -> str:
    intake = application.intake
    dev = match.device
    s = match.scores
    return (
        f"Applicant ID: {application.applicant_id}\n"
        f"Category: {application.category.value}\n"
        f"Urgency: {intake.urgency.value}, current tech access: {intake.current_tech_access.value}\n"
        f"Main usage: {intake.main_usage}\n"
        f"Software needed: {intake.software_needed}\n"
        f"Shared users: {intake.shared_user_count}\n"
        f"--- Device {dev.id} ---\n"
        f"Type: {dev.item_type.value}, tier: {dev.tier.value if dev.tier else 'n/a'}\n"
        f"Condition: {dev.condition}/5, available_from: {dev.available_from}\n"
        f"Specs: {dev.specs}\n"
        f"--- Scores ---\n"
        f"Priority: {s.priority:.2f}, Timing: {s.timing:.2f}, "
        f"Condition: {s.condition:.2f}, Efficiency: {s.efficiency:.2f}, "
        f"Composite: {s.composite:.2f}\n"
        "Write the 2-3 sentence rationale now."
    )


def _explain_fallback(application: Application, match: MatchResult) -> str:
    dev = match.device
    s = match.scores
    tier_phrase = f"a {dev.tier.value} device" if dev.tier else f"a {dev.item_type.value} device"
    return (
        f"Device {dev.id} is {tier_phrase} in condition {dev.condition}/5, "
        f"matching category {application.category.value} with composite score "
        f"{s.composite:.2f} (priority {s.priority:.2f}, timing {s.timing:.2f}, "
        f"condition {s.condition:.2f}, efficiency {s.efficiency:.2f})."
    )


# ---------------------------------------------------------------------------
# Task C — Parse free-text intake answers into IntakeAnswers
# ---------------------------------------------------------------------------


_PARSE_SYSTEM = (
    "You are a careful intake parser for a nonprofit hardware-allocation "
    "program. Given the raw answers a user typed in the terminal, return "
    "valid JSON matching the IntakeAnswers schema. Rules:\n"
    "- Unknown fields stay null or empty arrays.\n"
    "- `purpose` values are exactly: A1, A2, A3, B, C, D, E, F.\n"
    "- If Q3 mentioned 'computer science', 'software engineering', or 'coding', set a3_subtrack='software_engineering'.\n"
    "- Heavy software keywords (Photoshop, Premiere, VMs, Docker, ML frameworks) belong in software_needed exactly as named.\n"
    "- urgency: critical | high | medium | low.\n"
    "- current_tech_access: none | phone_only | shared_device | outdated_device | internet_only.\n"
    "- shared_user_count >= 1.\n"
    "- prior_device_status: working | broken | outgrown | n/a.\n"
    "Be conservative. If the user did not say something, do not make it up."
)


def parse_intake(raw_answers: dict[str, str]) -> IntakeAnswers:
    """Parse raw Q1..Q8 strings into a validated IntakeAnswers.

    `raw_answers` keys: q1, q2, q3 (optional), q4, q5, q6, q7, q8.
    Falls back to a heuristic parser if the LLM is unavailable so the engine
    is still demoable offline.
    """
    if not is_available():
        return _heuristic_parse(raw_answers)

    prompt = (
        "Raw answers (some may be free text, multi-select numbers like '1, 3', or short phrases):\n"
        f"{json.dumps(raw_answers, indent=2)}\n\n"
        "Question reference:\n"
        "Q1 — who is the device for (free text).\n"
        "Q2 — purpose, multi-select: 1=School (map to A based on Q3), 2=Work (C), "
        "3=Healthcare (B), 4=Personal/staying connected (E), 5=Newcomer (F), 6=Other.\n"
        "Q3 — only if Q2 includes school: 1=K-6 (A1), 2=Gr 8-HS (A2), 3=Post-sec (A3) + program name.\n"
        "Q4 — main_usage multi-select (numbered).\n"
        "Q5 — software_needed (free text; comma split; 'none' -> empty array).\n"
        "Q6 — free text: extract shared_user_count (int >= 1) and current_tech_access.\n"
        "Q7 — urgency: 1=critical, 2=high, 3=medium, 4=low.\n"
        "Q8 — free text: extract age_range, year_arrived_canada, employment_status, "
        "accessibility_needs (vision/mobility/hearing), applied_before, prior_device_status.\n\n"
        "Return JSON ONLY matching IntakeAnswers."
    )

    try:
        data = _generate_json(prompt, system=_PARSE_SYSTEM)
        # Validate against Pydantic
        return IntakeAnswers.model_validate(data)
    except Exception as exc:
        _audit({"task": "parse_intake_fallback", "error": str(exc), "raw": raw_answers})
        return _heuristic_parse(raw_answers)


# ---------------------------------------------------------------------------
# Heuristic fallback parser (offline / LLM-unavailable mode)
# ---------------------------------------------------------------------------


_PURPOSE_MAP = {
    "1": "A",  # school - resolved via Q3
    "2": "C",
    "3": "B",
    "4": "E",
    "5": "F",
}
_USAGE_MAP = {
    "1": "web browsing and email",
    "2": "video calls",
    "3": "writing documents",
    "4": "online classes",
    "5": "government or healthcare websites",
    "6": "programming or coding",
    "7": "graphic design or video editing",
    "8": "professional software",
    "9": "3D or gaming",
}
_URGENCY_MAP = {
    "1": "critical",
    "2": "high",
    "3": "medium",
    "4": "low",
}


def _multi_select(raw: str, table: dict[str, str]) -> list[str]:
    out: list[str] = []
    for chunk in raw.replace(";", ",").split(","):
        c = chunk.strip()
        if c in table:
            out.append(table[c])
    return out


def _heuristic_parse(raw: dict[str, str]) -> IntakeAnswers:
    from asra_matcher.taxonomy import (
        A3Subtrack,
        Category,
        PriorDeviceStatus,
        TechAccess,
        Urgency,
    )

    q1 = (raw.get("q1") or "").strip()
    q2 = (raw.get("q2") or "").strip()
    q3 = (raw.get("q3") or "").strip()
    q4 = (raw.get("q4") or "").strip()
    q5 = (raw.get("q5") or "").strip()
    q6 = (raw.get("q6") or "").strip()
    q7 = (raw.get("q7") or "").strip()
    q8 = (raw.get("q8") or "").strip()

    # Purpose
    purpose_codes: list[str] = []
    for chunk in q2.replace(";", ",").split(","):
        c = chunk.strip()
        if c in _PURPOSE_MAP:
            base = _PURPOSE_MAP[c]
            if base == "A":
                # resolve via Q3
                q3l = q3.lower()
                if q3l.startswith("1") or "k" in q3l[:3] or "grade 6" in q3l or "elementary" in q3l:
                    purpose_codes.append("A1")
                elif q3l.startswith("2") or "high school" in q3l or "grade 8" in q3l:
                    purpose_codes.append("A2")
                else:
                    purpose_codes.append("A3")
            else:
                purpose_codes.append(base)
    purpose = []
    for code in purpose_codes:
        try:
            purpose.append(Category(code))
        except ValueError:
            pass

    # A3 sub-track and program
    a3_subtrack = None
    program_name = None
    if Category.A3 in purpose:
        q3l = q3.lower()
        if any(k in q3l for k in ["computer science", "software", "coding", "programming", "comp sci"]):
            a3_subtrack = A3Subtrack.SOFTWARE_ENGINEERING
        elif any(k in q3l for k in ["art", "design", "music", "film", "media"]):
            a3_subtrack = A3Subtrack.ARTS
        elif any(k in q3l for k in ["business", "commerce", "finance", "account", "mba"]):
            a3_subtrack = A3Subtrack.BUSINESS
        elif any(k in q3l for k in ["science", "biology", "physics", "chem", "math", "engineering"]):
            a3_subtrack = A3Subtrack.SCIENCE
        program_name = q3 or None

    # Main usage
    main_usage = _multi_select(q4, _USAGE_MAP)

    # Software needed
    software: list[str] = []
    if q5 and q5.lower() != "none":
        software = [s.strip() for s in q5.split(",") if s.strip()]

    # Q6 — shared count + tech access
    shared = 1
    _NUM_WORDS = {
        "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
        "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    }
    for tok in q6.lower().replace(",", " ").split():
        if tok.isdigit():
            n = int(tok)
            if 1 <= n <= 20:
                shared = n
                break
        if tok in _NUM_WORDS:
            shared = _NUM_WORDS[tok]
            break
    q6l = q6.lower()
    if "no device" in q6l or "no computer" in q6l or "nothing" in q6l:
        tech_access = TechAccess.NONE
    elif "only phone" in q6l or "just phone" in q6l or "phone only" in q6l or "smartphone only" in q6l:
        tech_access = TechAccess.PHONE_ONLY
    elif "shared" in q6l or "borrow" in q6l:
        tech_access = TechAccess.SHARED_DEVICE
    elif "old" in q6l or "outdated" in q6l or "broken" in q6l or "slow" in q6l:
        tech_access = TechAccess.OUTDATED_DEVICE
    elif "internet" in q6l and "no" not in q6l:
        tech_access = TechAccess.INTERNET_ONLY
    else:
        tech_access = TechAccess.NONE

    # Urgency
    urgency = Urgency(_URGENCY_MAP.get(q7.strip(), "medium"))

    # Q8
    q8l = q8.lower()
    accessibility = []
    if "vision" in q8l or "eyes" in q8l or "blind" in q8l or "sight" in q8l:
        accessibility.append("vision")
    if "mobility" in q8l or "wheelchair" in q8l or "hands" in q8l:
        accessibility.append("mobility")
    if "hearing" in q8l or "deaf" in q8l:
        accessibility.append("hearing")
    age_range = None
    for marker in ["65+", "60+", "18-25", "25-40", "40-60"]:
        if marker in q8:
            age_range = marker
            break
    # year arrived
    year_arrived = None
    import re as _re
    m = _re.search(r"\b(19|20)\d{2}\b", q8)
    if m:
        year_arrived = int(m.group(0))
    applied_before = False
    prior = PriorDeviceStatus.NA
    if "received" in q8l or "applied before" in q8l or "previously" in q8l:
        applied_before = True
        if "still works" in q8l or "working" in q8l:
            prior = PriorDeviceStatus.WORKING
        elif "broken" in q8l:
            prior = PriorDeviceStatus.BROKEN
        elif "outgrown" in q8l or "too small" in q8l:
            prior = PriorDeviceStatus.OUTGROWN

    return IntakeAnswers(
        who_needs_it=q1 or "applicant",
        main_usage=main_usage,
        software_needed=software,
        shared_user_count=shared,
        urgency=urgency,
        purpose=purpose or [Category.E],
        current_tech_access=tech_access,
        a3_subtrack=a3_subtrack,
        program_name=program_name,
        age_range=age_range,
        year_arrived_canada=year_arrived,
        accessibility_needs=accessibility,
        applied_before=applied_before,
        prior_device_status=prior,
    )
