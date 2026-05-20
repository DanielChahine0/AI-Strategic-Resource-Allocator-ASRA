"""End-to-end engine: split → fit-gate → RAG-narrow tier → score → rank → explain."""
from __future__ import annotations

from datetime import date
from typing import Callable, Iterable

from . import rules as rules_mod
from . import scoring as scoring_mod
from . import splitter as splitter_mod
from .llm import (
    MatchExplanation,
    TierRecommendation,
    explain_matches as llm_explain_matches,
    recommend_tier as llm_recommend_tier,
)
from .models import (
    Applicant,
    Application,
    Device,
    FinalMatchResult,
    MatchResult,
)
from .taxonomy import Category, DeviceTier


def match(
    applicant: Applicant,
    inventory: Iterable[Device],
    *,
    today: date | None = None,
    tier_recommender: Callable[[Application], TierRecommendation] | None = None,
    explainer: Callable[[Application, list[Device]], MatchExplanation] | None = None,
) -> FinalMatchResult:
    """Run the full pipeline for an applicant and return a FinalMatchResult.

    `tier_recommender` and `explainer` are injectable so tests can replace the
    LLM calls without touching the network.
    """
    today = today or date.today()
    tier_recommender = tier_recommender or llm_recommend_tier
    explainer = explainer or llm_explain_matches

    inventory_list = list(inventory)
    applications = splitter_mod.split(applicant)

    per_app_top: list[tuple[Application, list[MatchResult], TierRecommendation | None]] = []

    for app in applications:
        rag_tier_rec: TierRecommendation | None = None
        rag_allowed: set[DeviceTier] | None = None
        if app.category in {Category.A3, Category.C}:
            rag_tier_rec = tier_recommender(app)
            # Allow only the recommended tier (and weaker — never over-allocate).
            rag_allowed = _tiers_at_or_below(rag_tier_rec.recommended_tier)

        ranked: list[MatchResult] = []
        for dev in inventory_list:
            if not rules_mod.fit_gate(dev, app, rag_allowed_tiers=rag_allowed):
                continue
            breakdown = scoring_mod.compute_all(
                dev,
                app,
                today=today,
                rag_recommended_tier=(
                    rag_tier_rec.recommended_tier if rag_tier_rec else None
                ),
            )
            ranked.append(
                MatchResult(
                    device=dev,
                    application_category=app.category,
                    breakdown=breakdown,
                )
            )
        ranked.sort(key=lambda r: r.breakdown.composite, reverse=True)
        per_app_top.append((app, ranked[:2], rag_tier_rec))

    # Pick the application whose #1 result has the highest composite.
    per_app_top.sort(
        key=lambda t: (t[1][0].breakdown.composite if t[1] else -1.0),
        reverse=True,
    )
    if not per_app_top or not per_app_top[0][1]:
        return FinalMatchResult(
            applicant_id=applicant.id,
            chosen_application=applications[0] if applications else _empty_app(applicant),
            top_matches=[],
            discarded_applications=[a for a, _, _ in per_app_top[1:]],
            notes=["No devices passed the fit gate for any application."],
        )

    chosen_app, top2, chosen_rag = per_app_top[0]
    discarded = [a for a, _, _ in per_app_top[1:]]

    explanation = explainer(chosen_app, [m.device for m in top2])
    for m in top2:
        m.explanation = explanation.explanations.get(m.device.id)
        m.citations = explanation.citations.get(m.device.id, [])

    retrieval_trace: dict = {}
    if chosen_rag and chosen_rag.chunks:
        retrieval_trace["tier_recommendation"] = chosen_rag.chunks
    if explanation.chunks:
        retrieval_trace["explanation"] = explanation.chunks

    notes: list[str] = []
    if chosen_rag and chosen_rag.fallback_used:
        notes.append(
            "Tier recommendation fell back to a conservative default — review the audit log."
        )
    if explanation.fallback_used:
        notes.append("Explanation fell back to a deterministic template.")

    return FinalMatchResult(
        applicant_id=applicant.id,
        chosen_application=chosen_app,
        top_matches=top2,
        discarded_applications=discarded,
        retrieval_trace=retrieval_trace,
        explanations={m.device.id: (m.explanation or "") for m in top2},
        notes=notes,
    )


def _tiers_at_or_below(tier: DeviceTier) -> set[DeviceTier]:
    """Allow the recommended tier and weaker tiers (avoid over-allocating power)."""
    order = [DeviceTier.T1, DeviceTier.T2, DeviceTier.T3]
    if tier not in order:
        return {DeviceTier.T2, DeviceTier.T3}
    idx = order.index(tier)
    return set(order[idx:])


def _empty_app(applicant: Applicant) -> Application:
    return Application(
        applicant_id=applicant.id,
        submitted_at=applicant.submitted_at,
        category=Category.E,
        intake=applicant.intake,
    )
