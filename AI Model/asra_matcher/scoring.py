"""Pure scoring functions. All scores live in [0.0, 1.0].

Fit is a hard gate, not a weighted score — see `fit_gate`. The other four
dimensions (priority, timing, condition, efficiency) combine into a composite
via WEIGHTS.

Every weight, urgency window, and bonus constant in this module is listed in
README "Tunable knobs" and should be treated as a stakeholder-tunable knob,
not a refactor target.
"""

from __future__ import annotations

from datetime import date

from asra_matcher import rules
from asra_matcher.models import Application, Device, ScoreBreakdown
from asra_matcher.taxonomy import (
    TIER_RANK,
    URGENCY_WINDOW_DAYS,
    Category,
    DeviceTier,
    ItemType,
    PriorDeviceStatus,
    TechAccess,
    Urgency,
)

# --- Composite weights (Open Question §11.3) ------------------------------

WEIGHTS: dict[str, float] = {
    "priority":   0.35,
    "timing":     0.25,
    "condition":  0.20,
    "efficiency": 0.20,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Composite weights must sum to 1.0"

# --- Priority bonuses (Open Question §11.4) -------------------------------

URGENCY_BASE = {
    Urgency.CRITICAL: 1.00,
    Urgency.HIGH:     0.75,
    Urgency.MEDIUM:   0.50,
    Urgency.LOW:      0.25,
}
BONUS_NO_TECH = 0.10
BONUS_LARGE_HOUSEHOLD = 0.05
BONUS_B_OR_C_CATEGORY = 0.05
BONUS_LONG_WAITLIST = 0.05
PENALTY_REPEAT_WORKING = -0.10

LARGE_HOUSEHOLD_THRESHOLD = 3
LONG_WAITLIST_THRESHOLD_DAYS = 60


# ---------------------------------------------------------------------------
# Fit gate
# ---------------------------------------------------------------------------


def fit_gate(device: Device, application: Application) -> tuple[bool, list[str]]:
    """Hard gate. Returns (fit, reasons_if_excluded).

    A device is excluded if ANY of:
      - Item-type mismatch (e.g. applicant needs a computer, this is a cable)
      - Computer tier violates the direct-linking rules for the category
      - Required software cannot run on the tier
      - Accessibility hard requirement unmet
    """
    reasons: list[str] = []
    category = application.category
    intake = application.intake

    # ---- Item-type gate ----
    if device.item_type == ItemType.COMPUTER:
        # Always eligible to be a primary device, subject to tier check below.
        pass
    elif device.item_type == ItemType.MOBILE:
        if rules.mobile_blocked(category):
            reasons.append(f"Category {category.value} cannot receive mobile devices")
        elif not rules.mobile_allowed(category):
            # Non-mobile-eligible categories still need a computer.
            reasons.append(f"Category {category.value} requires a computer, not mobile")
    else:
        # Peripherals / displays / connectivity: not standalone primary devices.
        reasons.append(f"Item type {device.item_type.value} is not a primary device")

    # ---- Tier gate (computers only) ----
    if device.item_type == ItemType.COMPUTER and device.tier is not None:
        if device.tier == DeviceTier.OTHER:
            reasons.append("Device tier OTHER cannot be auto-matched")
        else:
            allowed = rules.allowed_tiers(category, intake)
            if device.tier not in allowed:
                reasons.append(
                    f"Tier {device.tier.value} not in allowed set "
                    f"{sorted(t.value for t in allowed)} for category {category.value}"
                )

        # Software capability check.
        if not rules.device_meets_software(device.tier, intake.software_needed):
            reasons.append(
                f"Tier {device.tier.value} cannot run requested software: "
                f"{intake.software_needed}"
            )

    # ---- Accessibility gate ----
    needs = {n.lower() for n in intake.accessibility_needs}
    if "vision" in needs or "large display" in needs:
        # Standalone mobile phones generally don't satisfy vision needs.
        if device.item_type == ItemType.MOBILE and "phone" in (device.notes or "").lower():
            reasons.append("Vision accessibility need not met by phone-only device")

    return (len(reasons) == 0, reasons)


# ---------------------------------------------------------------------------
# Efficiency
# ---------------------------------------------------------------------------


def efficiency_score(device: Device, application: Application) -> float:
    """Penalise over-allocation (giving a more powerful device than needed).

    over_alloc = max(0, device_rank - needed_rank)
    efficiency = 1 - over_alloc / 2   (since max gap is T1 given when T3 needed)
    """
    if device.item_type != ItemType.COMPUTER or device.tier is None:
        return 1.0
    if device.tier == DeviceTier.OTHER:
        return 0.5
    needed = rules.needed_tier(application.category, application.intake)
    over_alloc = max(0, TIER_RANK[device.tier] - TIER_RANK[needed])
    return max(0.0, 1.0 - over_alloc / 2.0)


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------


def timing_score(device: Device, application: Application, today: date | None = None) -> float:
    """Compare device availability against the urgency window.

    days_late = max(0, available_from - today - window_days)
    timing = clamp(1 - days_late / window_days, 0, 1)

    `today` is injectable for deterministic tests.
    """
    today = today or date.today()
    urgency = application.intake.urgency
    window = URGENCY_WINDOW_DAYS[urgency]
    days_until_available = (device.available_from - today).days
    days_late = max(0, days_until_available - window)
    return max(0.0, min(1.0, 1.0 - days_late / window))


# ---------------------------------------------------------------------------
# Priority
# ---------------------------------------------------------------------------


def priority_score(application: Application) -> float:
    """Compute applicant priority from intake signals.

    Default formula (every weight is a tunable knob — see §11.4):
      base = URGENCY_BASE[urgency]
      + 0.10 if current_tech_access == NONE
      + 0.05 if shared_user_count >= 3
      + 0.05 if purpose includes B or C
      + 0.05 if waitlist_days > 60
      - 0.10 if applied_before AND prior_device_status == WORKING
      clamp to [0, 1]
    """
    intake = application.intake
    score = URGENCY_BASE[intake.urgency]

    if intake.current_tech_access == TechAccess.NONE:
        score += BONUS_NO_TECH
    if intake.shared_user_count >= LARGE_HOUSEHOLD_THRESHOLD:
        score += BONUS_LARGE_HOUSEHOLD
    if Category.B in intake.purpose or Category.C in intake.purpose:
        score += BONUS_B_OR_C_CATEGORY
    if intake.waitlist_days > LONG_WAITLIST_THRESHOLD_DAYS:
        score += BONUS_LONG_WAITLIST
    if intake.applied_before and intake.prior_device_status == PriorDeviceStatus.WORKING:
        score += PENALTY_REPEAT_WORKING

    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# Condition
# ---------------------------------------------------------------------------


def condition_score(device: Device, application: Application) -> float:
    """Device condition normalised to [0, 1], with a small extra penalty for
    long-horizon users (Seniors, Newcomers) when condition is below 3."""
    base = device.condition / 5.0
    long_horizon = {Category.D, Category.F}
    if application.category in long_horizon and device.condition < 3:
        base = max(0.0, base - 0.10)
    return max(0.0, min(1.0, base))


# ---------------------------------------------------------------------------
# Composite
# ---------------------------------------------------------------------------


def compute_all(
    device: Device,
    application: Application,
    today: date | None = None,
) -> ScoreBreakdown:
    """Compute every dimension and the composite for one (device, application).

    If the fit gate fails, composite is 0 and reasons are listed in `notes`.
    """
    fit, reasons = fit_gate(device, application)

    eff = efficiency_score(device, application)
    tim = timing_score(device, application, today=today)
    pri = priority_score(application)
    con = condition_score(device, application)

    composite = (
        WEIGHTS["priority"] * pri
        + WEIGHTS["timing"] * tim
        + WEIGHTS["condition"] * con
        + WEIGHTS["efficiency"] * eff
    ) if fit else 0.0

    return ScoreBreakdown(
        fit=fit,
        efficiency=eff,
        timing=tim,
        priority=pri,
        condition=con,
        composite=composite,
        notes=reasons,
    )
