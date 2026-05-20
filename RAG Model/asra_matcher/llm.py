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
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .models import (
    Application,
    Device,
    IntakeAnswers,
    RagContext,
    RetrievedChunk,
)
from .rag import prompts, retrieve as retrieve_mod
from .taxonomy import Category, DeviceTier

DEFAULT_GEN_MODEL = "gemini-2.5-flash-lite"
TEMP_PARSE = 0.1
TEMP_TIER = 0.1
TEMP_EXPLAIN = 0.4


def _model() -> str:
    return os.environ.get("ASRA_GENERATION_MODEL", DEFAULT_GEN_MODEL)


def _audit_path() -> Path:
    return Path(os.environ.get("ASRA_LLM_AUDIT_LOG", "./logs/llm_audit.jsonl"))


def _audit(record: dict[str, Any]) -> None:
    p = _audit_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


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


# ---------------------------------------------------------------------------
# Low-level generation
# ---------------------------------------------------------------------------


def _client():
    from google import genai  # type: ignore

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def _generate(
    system: str,
    user: str,
    *,
    temperature: float,
    json_mode: bool = True,
) -> str:
    """Single call to Gemini. Returns raw text. One retry on transient error."""
    from google.genai import types  # type: ignore

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            client = _client()
            cfg_kwargs: dict[str, Any] = {
                "temperature": temperature,
                "system_instruction": system,
            }
            if json_mode:
                cfg_kwargs["response_mime_type"] = "application/json"
            cfg = types.GenerateContentConfig(**cfg_kwargs)
            resp = client.models.generate_content(
                model=_model(), contents=user, config=cfg
            )
            return resp.text or ""
        except Exception as exc:
            last_exc = exc
            time.sleep(0.5)
    assert last_exc is not None
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


# ---------------------------------------------------------------------------
# Task A — tier recommendation
# ---------------------------------------------------------------------------


def recommend_tier(
    application: Application,
    *,
    retrieve_fn=None,
    generate_fn=None,
    today: Optional[datetime] = None,
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

    schema = IntakeAnswers.model_json_schema()
    ctx = RagContext(task="parse_intake", chunks=chunks)
    system, user = prompts.intake_parse_prompt(raw_answers, schema, ctx)

    raw = ""
    parsed_json: dict[str, Any] | None = None
    error: str | None = None
    fallback_used = False
    try:
        gen = generate_fn or _generate
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
