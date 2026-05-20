"""Scoring functions: fit gate, efficiency, timing, priority, condition."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from asra_matcher import scoring
from asra_matcher.models import Application, Device
from asra_matcher.taxonomy import (
    Category,
    DeviceTier,
    ItemType,
    PriorDeviceStatus,
    TechAccess,
    Urgency,
)
from tests.conftest import FIXED_TODAY, make_applicant


# ---- Fit gate ------------------------------------------------------------


def test_B_excluded_from_T1(t1_device):
    app = make_applicant(purpose=[Category.B]).intake
    application = Application(applicant_id="a", category=Category.B, intake=app)
    fit, reasons = scoring.fit_gate(t1_device, application)
    assert not fit
    assert any("T1" in r for r in reasons)


def test_A1_excluded_from_T2(t2_device):
    application = Application(
        applicant_id="a",
        category=Category.A1,
        intake=make_applicant(purpose=[Category.A1]).intake,
    )
    fit, _ = scoring.fit_gate(t2_device, application)
    assert not fit


def test_E_blocks_mobile(mobile_device):
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(purpose=[Category.E]).intake,
    )
    fit, reasons = scoring.fit_gate(mobile_device, application)
    assert not fit
    assert any("mobile" in r.lower() for r in reasons)


def test_F_accepts_mobile(mobile_device):
    application = Application(
        applicant_id="a",
        category=Category.F,
        intake=make_applicant(purpose=[Category.F]).intake,
    )
    fit, _ = scoring.fit_gate(mobile_device, application)
    assert fit


def test_T3_blocked_by_photoshop_requirement(t3_device, make_applicant_fn):
    application = Application(
        applicant_id="a",
        category=Category.A3,
        intake=make_applicant_fn(
            purpose=[Category.A3],
            software=["Adobe Photoshop"],
        ).intake,
    )
    fit, reasons = scoring.fit_gate(t3_device, application)
    assert not fit
    assert any("software" in r.lower() for r in reasons)


# ---- Efficiency ----------------------------------------------------------


def test_efficiency_penalises_T1_when_T3_needed(t1_device):
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(purpose=[Category.E]).intake,
    )
    # T1 given when T3 needed -> 2 ranks over -> efficiency = 0
    assert scoring.efficiency_score(t1_device, application) == 0.0


def test_efficiency_perfect_when_T3_for_T3(t3_device):
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(purpose=[Category.E]).intake,
    )
    assert scoring.efficiency_score(t3_device, application) == 1.0


def test_efficiency_T2_for_T3_is_half(t2_device):
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(purpose=[Category.E]).intake,
    )
    assert scoring.efficiency_score(t2_device, application) == 0.5


# ---- Timing --------------------------------------------------------------


def test_timing_perfect_when_available_within_window(t3_device):
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(purpose=[Category.E], urgency=Urgency.HIGH).intake,
    )
    # available 2026-05-14, today 2026-05-11, high window 30 days -> well inside
    assert scoring.timing_score(t3_device, application, today=FIXED_TODAY) == 1.0


def test_timing_zero_when_far_past_window():
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(purpose=[Category.E], urgency=Urgency.CRITICAL).intake,
    )
    far_future = FIXED_TODAY + timedelta(days=60)
    device = Device(
        id="late",
        item_type=ItemType.COMPUTER,
        tier=DeviceTier.T3,
        condition=3,
        available_from=far_future,
    )
    # critical window = 7; days_late = 60-7 = 53; 1 - 53/7 < 0 -> clamped to 0
    assert scoring.timing_score(device, application, today=FIXED_TODAY) == 0.0


# ---- Priority ------------------------------------------------------------


def test_priority_clamps_at_one():
    application = Application(
        applicant_id="a",
        category=Category.C,
        intake=make_applicant(
            purpose=[Category.C, Category.B],
            urgency=Urgency.CRITICAL,
            tech_access=TechAccess.NONE,
            shared=4,
            waitlist_days=120,
        ).intake,
    )
    # base 1.0 + 0.10 + 0.05 + 0.05 + 0.05 = 1.25 -> clamped
    assert scoring.priority_score(application) == 1.0


def test_priority_repeat_applicant_penalty():
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(
            purpose=[Category.E],
            urgency=Urgency.MEDIUM,
            applied_before=True,
            prior=PriorDeviceStatus.WORKING,
        ).intake,
    )
    # base 0.50 - 0.10 = 0.40 (no other bonuses since tech_access=NONE adds 0.10)
    # Actually default tech_access is NONE in make_applicant -> +0.10
    # 0.50 + 0.10 - 0.10 = 0.50
    assert scoring.priority_score(application) == pytest.approx(0.50, abs=1e-6)


def test_priority_base_low_urgency_with_no_bonuses():
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(
            purpose=[Category.E],
            urgency=Urgency.LOW,
            tech_access=TechAccess.OUTDATED_DEVICE,
            shared=1,
            waitlist_days=0,
        ).intake,
    )
    assert scoring.priority_score(application) == pytest.approx(0.25)


# ---- Condition -----------------------------------------------------------


def test_condition_normalises_to_5ths(t3_device):
    application = Application(
        applicant_id="a",
        category=Category.E,
        intake=make_applicant(purpose=[Category.E]).intake,
    )
    assert scoring.condition_score(t3_device, application) == pytest.approx(3 / 5)


def test_condition_penalty_for_long_horizon_categories():
    poor = Device(
        id="poor",
        item_type=ItemType.COMPUTER,
        tier=DeviceTier.T3,
        condition=2,
        available_from=FIXED_TODAY,
    )
    senior_app = Application(
        applicant_id="a",
        category=Category.D,
        intake=make_applicant(purpose=[Category.D]).intake,
    )
    score = scoring.condition_score(poor, senior_app)
    # 2/5 = 0.40 then -0.10 penalty -> 0.30
    assert score == pytest.approx(0.30)


# ---- Composite -----------------------------------------------------------


def test_composite_is_zero_when_fit_fails(t1_device):
    app = Application(
        applicant_id="a",
        category=Category.B,
        intake=make_applicant(purpose=[Category.B]).intake,
    )
    breakdown = scoring.compute_all(t1_device, app, today=FIXED_TODAY)
    assert not breakdown.fit
    assert breakdown.composite == 0.0


def test_composite_weights_sum_to_one():
    assert sum(scoring.WEIGHTS.values()) == pytest.approx(1.0)
