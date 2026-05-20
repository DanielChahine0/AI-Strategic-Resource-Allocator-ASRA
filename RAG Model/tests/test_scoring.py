"""Score function tests."""
from __future__ import annotations

from datetime import date

from asra_matcher import scoring
from asra_matcher.models import Device
from asra_matcher.splitter import split
from asra_matcher.taxonomy import Category, DeviceTier, ItemType, Urgency


def _device(tier: DeviceTier, *, condition: int = 4, available_from=date(2026, 5, 12)) -> Device:
    return Device(
        id=f"DEV-{tier.value}",
        item_type=ItemType.COMPUTER,
        tier=tier,
        specs={},
        condition=condition,
        available_from=available_from,
    )


def test_priority_scaling_with_urgency(make_applicant):
    today = date(2026, 5, 12)
    app = split(make_applicant(Category.E, urgency=Urgency.LOW))[0]
    assert scoring.priority_score(app) == 0.25

    app = split(make_applicant(Category.E, urgency=Urgency.CRITICAL))[0]
    # +0.10 (no device) → clamped at 1.0
    assert scoring.priority_score(app) == 1.0


def test_priority_clamps_at_one(make_applicant):
    app = split(
        make_applicant(
            Category.C,
            urgency=Urgency.CRITICAL,
            shared_user_count=5,
            current_tech_access={"has_internet": True, "device_situation": "none", "notes": None},
        )
    )[0]
    # 1.0 + 0.10 + 0.05 + 0.05 → clamped to 1.0
    assert scoring.priority_score(app) == 1.0


def test_timing_returns_full_when_inside_window(make_applicant):
    today = date(2026, 5, 12)
    app = split(make_applicant(Category.A1, urgency=Urgency.CRITICAL))[0]
    d = _device(DeviceTier.T3, available_from=today)
    assert scoring.timing_score(d, app, today=today) == 1.0


def test_timing_decays_outside_window(make_applicant):
    today = date(2026, 5, 12)
    # critical window is 7 days; device available in 14 → 7 days late → 0.0
    app = split(make_applicant(Category.A1, urgency=Urgency.CRITICAL))[0]
    d = _device(DeviceTier.T3, available_from=date(2026, 5, 26))
    assert scoring.timing_score(d, app, today=today) == 0.0


def test_condition_score_simple():
    d = _device(DeviceTier.T2, condition=3)
    assert scoring.condition_score(d) == 0.6


def test_efficiency_penalizes_over_allocation(make_applicant):
    # A1 needs T3 (rank 1). T1 (rank 3) over-allocates by 2 → efficiency = 0.
    app = split(make_applicant(Category.A1))[0]
    e = scoring.efficiency_score(_device(DeviceTier.T1), app)
    assert e == 0.0
    e = scoring.efficiency_score(_device(DeviceTier.T2), app)
    assert e == 0.5
    e = scoring.efficiency_score(_device(DeviceTier.T3), app)
    assert e == 1.0


def test_composite_uses_weights(make_applicant):
    scores = {"priority": 1.0, "timing": 1.0, "condition": 1.0, "efficiency": 1.0}
    assert scoring.composite(scores) == 1.0
    scores = {"priority": 0.0, "timing": 0.0, "condition": 0.0, "efficiency": 0.0}
    assert scoring.composite(scores) == 0.0


def test_compute_all_returns_breakdown(make_applicant):
    today = date(2026, 5, 12)
    app = split(make_applicant(Category.A1, urgency=Urgency.CRITICAL))[0]
    d = _device(DeviceTier.T3, condition=5, available_from=today)
    b = scoring.compute_all(d, app, today=today)
    assert 0.0 <= b.composite <= 1.0
    assert b.priority > 0.9  # critical + no device → high
    assert b.timing == 1.0
    assert b.condition == 1.0
    assert b.efficiency == 1.0
