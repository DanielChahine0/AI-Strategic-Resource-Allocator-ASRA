"""Sequential batch runner for the simplified allocator, with live progress.

Runs many applicants first-come-first-serve, spreading Gemini calls across the
key pool (so several free-tier keys multiply the daily quota). Applicants are
grouped — by area (e.g. Etobicoke) or plain submission order — into batches so a
long run can be paced and watched.

The whole run is wrapped in ONE token capture, so each applicant's spend is
attributed (via simple.allocate's per-step ledger) and the run total is exact.
A `progress_cb(done, total, item)` hook fires after every applicant; the CLI/API
use it to narrate progress live (a streaming UI is Phase 6).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime

from pydantic import BaseModel, Field

from asra_matcher import llm, sheets, simple
from asra_matcher.models import Device
from asra_matcher.obslog import get_logger

_log = get_logger("ai")

GROUP_BY_CHOICES = ("submission", "area", "none")


class BatchItem(BaseModel):
    applicant_id: str
    area: str | None = None
    group: str
    matched_device_id: str | None = None
    matched_tier: str | None = None
    composite: float = 0.0
    used_ai: bool = False
    tokens_total: int = 0
    token_steps: list[simple.TokenStep] = Field(default_factory=list)
    explanation: str | None = None


class BatchResult(BaseModel):
    total: int
    batches: int
    batch_size: int
    group_by: str
    groups: dict[str, int]
    tokens_total: int
    avg_tokens_per_applicant: float
    used_ai_count: int
    fallback_count: int
    unmatched_count: int
    wall_time_ms: float
    items: list[BatchItem]
    key_pool: list[dict] = Field(default_factory=list)


def _group_key(app: simple.SimpleApplicant, group_by: str) -> str:
    if group_by == "area":
        return (app.area or "unknown").strip() or "unknown"
    return "all"


def _fcfs_key(app: simple.SimpleApplicant):
    # First-come-first-serve: earliest submission first; undated sort last.
    return app.submitted_at or datetime.max


def run_batch(
    applicants: list[simple.SimpleApplicant],
    inventory: list[Device] | None = None,
    *,
    group_by: str = "submission",
    batch_size: int = 10,
    top_n: int | None = None,
    progress_cb: Callable[[int, int, BatchItem], None] | None = None,
) -> BatchResult:
    """Allocate a list of applicants FCFS and return per-applicant + aggregate results."""
    if group_by not in GROUP_BY_CHOICES:
        group_by = "submission"
    t0 = time.perf_counter()

    if inventory is None:
        inventory, _counts = sheets.load_inventory()

    # Group, then order FCFS within each group; concatenate groups.
    grouped: dict[str, list[simple.SimpleApplicant]] = {}
    for a in applicants:
        grouped.setdefault(_group_key(a, group_by), []).append(a)
    ordered: list[tuple[str, simple.SimpleApplicant]] = []
    for g in sorted(grouped):
        for a in sorted(grouped[g], key=_fcfs_key):
            ordered.append((g, a))

    total = len(ordered)
    n_batches = (total + batch_size - 1) // batch_size if batch_size > 0 else 1
    _log.info(
        "════════ BATCH START [AI] ════════ %d applicants · group_by=%s · %d batch(es) of %d · "
        "keys live=%d/%d",
        total, group_by, n_batches, batch_size, llm._pool().live_count(), len(llm._pool()),
    )

    items: list[BatchItem] = []
    # One capture wraps the whole run; simple.allocate diffs against it per call.
    llm.start_token_capture()
    try:
        for idx, (g, a) in enumerate(ordered):
            if batch_size > 0 and idx % batch_size == 0:
                _log.info("──── batch %d/%d ────", idx // batch_size + 1, n_batches)
            res = simple.allocate(a, inventory, top_n=top_n)
            top = res.top[0] if res.top else None
            item = BatchItem(
                applicant_id=a.applicant_id,
                area=a.area,
                group=g,
                matched_device_id=top.device.id if top else None,
                matched_tier=(top.device.tier.value if top and top.device.tier else None),
                composite=top.score.composite if top else 0.0,
                used_ai=res.used_ai,
                tokens_total=res.tokens_total,
                token_steps=res.token_steps,
                explanation=top.explanation if top else None,
            )
            items.append(item)
            _log.info(
                "  [%d/%d] %-18s grp=%-10s → %-16s tok=%-4d %s",
                idx + 1, total, a.applicant_id, g,
                item.matched_device_id or "—", item.tokens_total,
                "ai" if res.used_ai else "det",
            )
            if progress_cb is not None:
                progress_cb(idx + 1, total, item)
    finally:
        led = llm.read_token_capture() or {}
        llm.stop_token_capture()

    wall_ms = (time.perf_counter() - t0) * 1000.0
    tokens_total = int(led.get("total", 0))
    used_ai_count = sum(1 for it in items if it.used_ai)
    unmatched = sum(1 for it in items if it.matched_device_id is None)
    group_counts: dict[str, int] = {}
    for it in items:
        group_counts[it.group] = group_counts.get(it.group, 0) + 1

    _log.info(
        "════════ BATCH DONE  [AI] ════════ %d matched / %d unmatched · %d used AI · %d tokens · %.0fms",
        total - unmatched, unmatched, used_ai_count, tokens_total, wall_ms,
    )

    return BatchResult(
        total=total,
        batches=n_batches,
        batch_size=batch_size,
        group_by=group_by,
        groups=group_counts,
        tokens_total=tokens_total,
        avg_tokens_per_applicant=round(tokens_total / total, 1) if total else 0.0,
        used_ai_count=used_ai_count,
        fallback_count=total - used_ai_count,
        unmatched_count=unmatched,
        wall_time_ms=round(wall_ms, 1),
        items=items,
        key_pool=llm._pool().status(),
    )
