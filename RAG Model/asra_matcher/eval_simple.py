"""Impact harness for the simplified Q1–Q4 allocator (RAG variant).

Loads the simplified mock applicants (which answer only Q1–Q4), optionally
filters them to one area (e.g. Etobicoke), runs them first-come-first-serve
through the batch pipeline against the live refurbished inventory, and rolls the
result up into an "impact" report: how many people were matched, how many tokens
it cost, and how much of the work the deterministic algorithm did without the
LLM.

The dataset lives at repo-root `sample_simple/applicants.json` so both models
score byte-identical applicants.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

from . import batch, sheets, simple
from .models import Device

_DATA = Path(__file__).resolve().parents[2] / "sample_simple" / "applicants.json"


class ImpactReport(BaseModel):
    dataset: str
    area_filter: str | None = None
    applicants: int
    matched: int
    unmatched: int
    match_rate: float
    inventory_available: int
    tokens_total: int
    avg_tokens_per_applicant: float
    resolved_with_ai: int
    resolved_deterministically: int
    by_area: dict[str, int] = Field(default_factory=dict)
    by_matched_tier: dict[str, int] = Field(default_factory=dict)
    wall_time_ms: float = 0.0
    batch: batch.BatchResult


def load_applicants(area: str | None = None) -> list[simple.SimpleApplicant]:
    raw = json.loads(_DATA.read_text(encoding="utf-8"))
    apps = [simple.SimpleApplicant.model_validate(a) for a in raw]
    if area:
        a = area.strip().lower()
        apps = [x for x in apps if (x.area or "").strip().lower() == a]
    return apps


def run_impact(
    area: str | None = None,
    inventory: list[Device] | None = None,
    *,
    group_by: str = "area",
    batch_size: int = 10,
) -> ImpactReport:
    """Run the simplified dataset (optionally one area) and summarise the impact."""
    t0 = time.perf_counter()
    applicants = load_applicants(area)
    if inventory is None:
        inventory, _counts = sheets.load_inventory()

    result = batch.run_batch(
        applicants, inventory, group_by=group_by, batch_size=batch_size
    )

    by_tier: dict[str, int] = {}
    for it in result.items:
        if it.matched_tier:
            by_tier[it.matched_tier] = by_tier.get(it.matched_tier, 0) + 1

    matched = result.total - result.unmatched_count
    return ImpactReport(
        dataset="simple",
        area_filter=area,
        applicants=result.total,
        matched=matched,
        unmatched=result.unmatched_count,
        match_rate=round(matched / result.total, 3) if result.total else 0.0,
        inventory_available=len(inventory),
        tokens_total=result.tokens_total,
        avg_tokens_per_applicant=result.avg_tokens_per_applicant,
        resolved_with_ai=result.used_ai_count,
        resolved_deterministically=result.total - result.used_ai_count,
        by_area=result.groups,
        by_matched_tier=by_tier,
        wall_time_ms=round((time.perf_counter() - t0) * 1000.0, 1),
        batch=result,
    )
