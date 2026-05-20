"""Pure scoring functions. All scores normalize to [0.0, 1.0]."""
from __future__ import annotations

from datetime import date

from .models import Application, Device, ScoreBreakdown
from .taxonomy import Category, DeviceTier, URGENCY_WINDOW_DAYS, TIER_RANK


WEIGHTS = {"priority": 0.35, "timing": 0.25, "condition": 0.20, "efficiency": 0.20}


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def priority_score(app: Application) -> float:
    """Built only from the 7 intake fields."""
    urgency_base = {
        "critical": 1.0,
        "high": 0.75,
        "medium": 0.5,
        "low": 0.25,
    }[app.intake.urgency.value]
    score = urgency_base
    access = app.intake.current_tech_access
    if access and access.device_situation and access.device_situation.value == "none":
        score += 0.10
    if app.intake.shared_user_count >= 3:
        score += 0.05
    if app.category in {Category.B, Category.C}:
        score += 0.05
    return _clamp(score)


def timing_score(device: Device, app: Application, *, today: date | None = None) -> float:
    today = today or date.today()
    window = URGENCY_WINDOW_DAYS[app.intake.urgency]
    delta_days = (device.available_from - today).days
    # days_late > 0 when device becomes available after the urgency window closes.
    days_late = max(0, delta_days - window)
    return _clamp(1.0 - (days_late / window))


def condition_score(device: Device) -> float:
    return _clamp(device.condition / 5.0)


def _needed_rank(app: Application, rag_recommended_tier: DeviceTier | None) -> int:
    """The minimum tier rank an applicant needs.

    For direct-linked categories, derive from the allowed set's maximum (the
    spec already says exactly what they get). For RAG-decided categories, use
    the LLM's recommendation if provided, else fall back to T2.
    """
    from .rules import allowed_tiers  # local import to avoid cycle at module load

    if rag_recommended_tier is not None:
        return TIER_RANK[rag_recommended_tier]
    allowed = allowed_tiers(app.category)
    if allowed:
        return max(TIER_RANK[t] for t in allowed)
    return TIER_RANK[DeviceTier.T2]


def efficiency_score(
    device: Device,
    app: Application,
    *,
    rag_recommended_tier: DeviceTier | None = None,
) -> float:
    if device.tier is None or device.tier == DeviceTier.OTHER:
        return 0.5  # neutral for peripherals; they shouldn't reach scoring anyway
    needed = _needed_rank(app, rag_recommended_tier)
    over_alloc = max(0, TIER_RANK[device.tier] - needed)
    # 2 = max possible over-allocation (T1 vs T3 needed) → score 0.
    return _clamp(1.0 - (over_alloc / 2.0))


def composite(scores: dict[str, float]) -> float:
    total = 0.0
    for k, w in WEIGHTS.items():
        total += w * scores.get(k, 0.0)
    return _clamp(total)


def compute_all(
    device: Device,
    app: Application,
    *,
    today: date | None = None,
    rag_recommended_tier: DeviceTier | None = None,
) -> ScoreBreakdown:
    p = priority_score(app)
    t = timing_score(device, app, today=today)
    c = condition_score(device)
    e = efficiency_score(device, app, rag_recommended_tier=rag_recommended_tier)
    comp = composite({"priority": p, "timing": t, "condition": c, "efficiency": e})
    return ScoreBreakdown(
        fit=True,
        priority=p,
        timing=t,
        condition=c,
        efficiency=e,
        composite=comp,
        weights=dict(WEIGHTS),
    )
