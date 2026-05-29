"""Orchestrate the full match pipeline.

split -> filter -> score -> rank -> select top 2 -> pick winning application
-> ask LLM for human-readable explanations.
"""

from __future__ import annotations

from datetime import date

from asra_matcher import llm, scoring, splitter
from asra_matcher.models import (
    Applicant,
    Application,
    ApplicationResult,
    Device,
    FinalMatchResult,
    MatchResult,
)


def match(
    applicant: Applicant,
    inventory: list[Device],
    today: date | None = None,
) -> FinalMatchResult:
    """Run the full pipeline and return the top 2 matches for the winning split."""
    applications = splitter.split(applicant)

    per_app_results: list[ApplicationResult] = []
    for app in applications:
        result = _score_application(app, inventory, today=today)
        per_app_results.append(result)

    # Pick the application whose #1 candidate has the highest composite.
    per_app_results.sort(key=lambda r: r.best_composite, reverse=True)
    winner = per_app_results[0]
    discarded = per_app_results[1:]

    # Ask the LLM for explanations on the winning top-2 only.
    if winner.top2:
        explanations = llm.explain_matches(winner.application, winner.top2)
        for match_obj, explanation in zip(winner.top2, explanations, strict=False):
            match_obj.explanation = explanation

    return FinalMatchResult(
        applicant_id=applicant.applicant_id,
        selected_application=winner,
        discarded_applications=discarded,
    )


def _score_application(
    application: Application,
    inventory: list[Device],
    today: date | None = None,
) -> ApplicationResult:
    """Score every device against one application, return the top 2."""
    candidates: list[MatchResult] = []
    for device in inventory:
        breakdown = scoring.compute_all(device, application, today=today)
        if not breakdown.fit:
            continue
        candidates.append(MatchResult(device=device, scores=breakdown))

    candidates.sort(key=lambda c: c.scores.composite, reverse=True)
    top2 = candidates[:2]
    best = top2[0].scores.composite if top2 else 0.0

    return ApplicationResult(
        application=application,
        top2=top2,
        best_composite=best,
    )
