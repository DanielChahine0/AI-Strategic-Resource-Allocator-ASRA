"""Evaluation-run mode for the AI Model.

Runs the matching engine over a labelled dataset and emits, for every applicant,
the four metrics the comparison UI needs:

  * token usage   — Gemini prompt/candidate/total counts for the match (0 when
                    the LLM is unavailable and deterministic fallbacks run)
  * accuracy      — chosen category + tier vs. the ground-truth allocation
  * confidence    — a deterministic 0–1 score from composite + decisiveness
  * explanation   — a rubric score for whether the rationale cites the
    quality       applicant's own stated fields

The response contract (`EvalResult`) is intentionally **identical** to the RAG
Model's, so the frontend can run both and diff them field-for-field. Anything
model-specific (RAG citations, tier-recommendation confidence) is carried in
nullable fields that this model simply leaves empty.

`/match` and the rest of the engine are untouched — this module only *reads*
the existing pipeline.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field

from asra_matcher import engine, llm
from asra_matcher.models import Applicant, Device, MatchResult

# Fixed "today" so timing scores (and therefore the whole run) are reproducible
# regardless of the wall-clock date the eval is triggered on.
EVAL_TODAY = date(2026, 5, 20)

_DATA_DIR = Path(__file__).resolve().parent.parent / "sample_data"
_DATASETS = {"sample-v1": _DATA_DIR}


# ---------------------------------------------------------------------------
# Response contract (shared, byte-for-byte, with the RAG Model)
# ---------------------------------------------------------------------------


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0
    total: int = 0


class AccuracyResult(BaseModel):
    category_correct: bool
    tier_correct: bool
    device_acceptable: bool | None = None
    score: float = Field(ge=0.0, le=1.0)


class ExplanationQuality(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    anchors_expected: list[str]
    anchors_present: list[str]
    cites_applicant_field: bool


class EvalRow(BaseModel):
    applicant_id: str
    scenario: str
    chosen_category: str | None = None
    chosen_device_id: str | None = None
    chosen_tier: str | None = None
    composite: float = 0.0
    runner_up_device_id: str | None = None
    runner_up_composite: float | None = None
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    accuracy: AccuracyResult | None = None
    confidence: float = 0.0
    explanation: str | None = None
    explanation_quality: ExplanationQuality | None = None
    citations: list[str] = Field(default_factory=list)
    tier_recommendation_confidence: float | None = None
    fallback_used: bool = False
    error: str | None = None


class EvalSummary(BaseModel):
    n: int
    tokens_input_total: int = 0
    tokens_output_total: int = 0
    tokens_total: int = 0
    avg_tokens_per_match: float = 0.0
    category_accuracy: float = 0.0
    tier_accuracy: float = 0.0
    device_accuracy: float = 0.0
    mean_accuracy_score: float = 0.0
    mean_confidence: float = 0.0
    mean_explanation_quality: float = 0.0
    fallback_rate: float = 0.0
    error_count: int = 0


class EvalResult(BaseModel):
    model: str
    dataset: str
    run_id: str
    wall_time_ms: float
    rows: list[EvalRow]
    summary: EvalSummary


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def available_datasets() -> list[str]:
    return sorted(_DATASETS)


def _load_dataset(dataset: str) -> tuple[list[Applicant], list[Device], dict]:
    base = _DATASETS.get(dataset)
    if base is None:
        raise ValueError(f"unknown dataset {dataset!r}; available: {available_datasets()}")

    applicants: list[Applicant] = []
    for path in sorted((base / "applicants").glob("*.json")):
        applicants.append(Applicant.model_validate_json(path.read_text()))

    inventory = [Device.model_validate(d) for d in json.loads((base / "inventory.json").read_text())]

    gt_path = base / "ground_truth.json"
    ground_truth = json.loads(gt_path.read_text()).get("applicants", {}) if gt_path.exists() else {}
    return applicants, inventory, ground_truth


# ---------------------------------------------------------------------------
# Metric scorers (deterministic — identical logic in both models)
# ---------------------------------------------------------------------------


def score_accuracy(
    chosen_category: str | None,
    chosen_tier: str | None,
    chosen_device_id: str | None,
    truth: dict | None,
) -> AccuracyResult | None:
    """Compare the chosen allocation to the ground-truth label.

    score = 0.5 * category_correct + 0.5 * tier_correct. Device match is a soft,
    reported-only signal (None when the label lists no acceptable devices).
    """
    if not truth:
        return None
    category_correct = chosen_category == truth.get("category")
    acceptable_tiers = truth.get("acceptable_tiers") or ([truth["tier"]] if truth.get("tier") else [])
    tier_correct = chosen_tier in acceptable_tiers if acceptable_tiers else False

    acceptable_devices = truth.get("acceptable_device_ids")
    device_acceptable: bool | None
    if acceptable_devices:
        device_acceptable = chosen_device_id in acceptable_devices
    else:
        device_acceptable = None

    score = 0.5 * float(category_correct) + 0.5 * float(tier_correct)
    return AccuracyResult(
        category_correct=category_correct,
        tier_correct=tier_correct,
        device_acceptable=device_acceptable,
        score=round(score, 3),
    )


def score_confidence(
    composite: float,
    runner_up_composite: float | None,
    fallback_used: bool,
) -> float:
    """Deterministic 0–1 confidence, identical formula in both models.

    Rewards a strong top score and a decisive margin over the runner-up;
    penalises any deterministic fallback. Kept model-agnostic (no LLM signal)
    so the two models' confidence numbers are directly comparable.
    """
    margin = composite - (runner_up_composite or 0.0)
    margin_norm = max(0.0, min(1.0, margin / 0.15))
    value = 0.6 * composite + 0.4 * margin_norm
    if fallback_used:
        value -= 0.15
    return round(max(0.0, min(1.0, value)), 3)


# Tier display synonyms so an explanation that says "high power" still counts
# as citing the T1 tier it was assigned.
_TIER_SYNONYMS = {
    "T1": ["t1", "high power", "high-power"],
    "T2": ["t2", "standard"],
    "T3": ["t3", "basic", "essential"],
}


def score_explanation_quality(
    explanation: str | None,
    *,
    software_needed: list[str],
    urgency: str,
    main_usage: list[str],
    tier: str | None,
) -> ExplanationQuality:
    """Reward explanations that ground themselves in the applicant's own fields.

    Anchors = each requested software package, the urgency word, the main-usage
    keywords, and the assigned tier. Score = fraction of anchors actually
    referenced in the text. `cites_applicant_field` is True when at least one
    *applicant* signal (software / urgency / usage) appears — the bar for a
    rationale that is about this person rather than generic boilerplate.
    """
    text = (explanation or "").lower()

    anchors: list[tuple[str, list[str]]] = []
    for sw in software_needed:
        anchors.append((sw, [sw.lower()]))
    if urgency:
        anchors.append((f"urgency:{urgency}", [urgency.lower()]))
    for usage in main_usage:
        # Use the most distinctive word of each usage phrase as the needle.
        word = max(usage.split(), key=len) if usage.split() else usage
        anchors.append((f"usage:{usage}", [word.lower()]))
    if tier:
        anchors.append((f"tier:{tier}", _TIER_SYNONYMS.get(tier, [tier.lower()])))

    expected = [label for label, _ in anchors]
    present = [label for label, needles in anchors if any(n and n in text for n in needles)]

    applicant_anchor_labels = {f"urgency:{urgency}"} | {sw for sw in software_needed} | {
        f"usage:{u}" for u in main_usage
    }
    cites_field = any(p in applicant_anchor_labels for p in present)

    score = (len(present) / len(expected)) if expected else (1.0 if text else 0.0)
    return ExplanationQuality(
        score=round(min(1.0, score), 3),
        anchors_expected=expected,
        anchors_present=present,
        cites_applicant_field=cites_field,
    )


# ---------------------------------------------------------------------------
# Run loop
# ---------------------------------------------------------------------------


def _evaluate_one(applicant: Applicant, inventory: list[Device], truth: dict) -> EvalRow:
    scenario = truth.get("scenario", applicant.applicant_id)
    ledger = llm.start_token_capture()
    try:
        result = engine.match(applicant, inventory, today=EVAL_TODAY)
    except Exception as exc:  # pragma: no cover - defensive: never fail the whole run
        llm.stop_token_capture()
        return EvalRow(applicant_id=applicant.applicant_id, scenario=scenario, error=repr(exc))
    finally:
        captured = llm.read_token_capture() or {}
        llm.stop_token_capture()

    selected = result.selected_application
    top2: list[MatchResult] = selected.top2
    chosen = top2[0] if top2 else None
    runner_up = top2[1] if len(top2) > 1 else None

    tokens = TokenUsage(
        input=int(captured.get("input", 0)),
        output=int(captured.get("output", 0)),
        total=int(captured.get("total", 0)),
    )
    # No Gemini calls landed (key missing or every call fell back) → fallback path.
    fallback_used = int(captured.get("calls", 0)) == 0

    if chosen is None:
        return EvalRow(
            applicant_id=applicant.applicant_id,
            scenario=scenario,
            chosen_category=selected.application.category.value,
            tokens=tokens,
            fallback_used=fallback_used,
            error="no device passed the fit gate",
        )

    chosen_tier = chosen.device.tier.value if chosen.device.tier else None
    composite = chosen.scores.composite
    runner_up_composite = runner_up.scores.composite if runner_up else None
    intake = selected.application.intake

    return EvalRow(
        applicant_id=applicant.applicant_id,
        scenario=scenario,
        chosen_category=selected.application.category.value,
        chosen_device_id=chosen.device.id,
        chosen_tier=chosen_tier,
        composite=round(composite, 3),
        runner_up_device_id=runner_up.device.id if runner_up else None,
        runner_up_composite=round(runner_up_composite, 3) if runner_up_composite is not None else None,
        tokens=tokens,
        accuracy=score_accuracy(selected.application.category.value, chosen_tier, chosen.device.id, truth),
        confidence=score_confidence(composite, runner_up_composite, fallback_used),
        explanation=chosen.explanation,
        explanation_quality=score_explanation_quality(
            chosen.explanation,
            software_needed=intake.software_needed,
            urgency=intake.urgency.value,
            main_usage=intake.main_usage,
            tier=chosen_tier,
        ),
        citations=[],  # RAG-only; always empty for the AI model
        tier_recommendation_confidence=None,  # AI engine doesn't call the LLM tier recommender
        fallback_used=fallback_used,
    )


def _summarize(rows: list[EvalRow]) -> EvalSummary:
    n = len(rows)
    scored = [r for r in rows if r.error is None]
    with_acc = [r for r in scored if r.accuracy is not None]

    def mean(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    tok_in = sum(r.tokens.input for r in rows)
    tok_out = sum(r.tokens.output for r in rows)
    tok_total = sum(r.tokens.total for r in rows)

    return EvalSummary(
        n=n,
        tokens_input_total=tok_in,
        tokens_output_total=tok_out,
        tokens_total=tok_total,
        avg_tokens_per_match=round(tok_total / n, 1) if n else 0.0,
        category_accuracy=mean([float(r.accuracy.category_correct) for r in with_acc]),
        tier_accuracy=mean([float(r.accuracy.tier_correct) for r in with_acc]),
        device_accuracy=mean(
            [float(r.accuracy.device_acceptable) for r in with_acc if r.accuracy.device_acceptable is not None]
        ),
        mean_accuracy_score=mean([r.accuracy.score for r in with_acc]),
        mean_confidence=mean([r.confidence for r in scored]),
        mean_explanation_quality=mean(
            [r.explanation_quality.score for r in scored if r.explanation_quality is not None]
        ),
        fallback_rate=mean([float(r.fallback_used) for r in rows]),
        error_count=n - len(scored),
    )


def run_eval(dataset: str = "sample-v1", limit: int | None = None) -> EvalResult:
    """Run the full evaluation over `dataset` and return per-row + aggregate results."""
    applicants, inventory, ground_truth = _load_dataset(dataset)
    if limit is not None:
        applicants = applicants[:limit]

    t0 = time.perf_counter()
    rows = [_evaluate_one(a, inventory, ground_truth.get(a.applicant_id, {})) for a in applicants]
    wall_ms = (time.perf_counter() - t0) * 1000.0

    return EvalResult(
        model="ai",
        dataset=dataset,
        run_id=uuid.uuid4().hex[:12],
        wall_time_ms=round(wall_ms, 1),
        rows=rows,
        summary=_summarize(rows),
    )
