"""Deterministic direct-linking rules from the LGT framework.

The LLM is consulted only for non-deterministic categories (A3, C). For
every other category, allowed tiers are fixed here.
"""

from __future__ import annotations

from asra_matcher.models import IntakeAnswers
from asra_matcher.taxonomy import A3Subtrack, Category, DeviceTier, ItemType

ALL_COMPUTER_TIERS: set[DeviceTier] = {DeviceTier.T1, DeviceTier.T2, DeviceTier.T3}


# Hard rules (Category -> allowed computer tiers).
# A3 and C return the full set because the LLM narrows them based on intake.
DIRECT_LINKING: dict[Category, set[DeviceTier]] = {
    Category.A1: {DeviceTier.T3},
    Category.A2: {DeviceTier.T2},
    Category.A3: ALL_COMPUTER_TIERS,  # LLM-decided
    Category.B:  {DeviceTier.T2, DeviceTier.T3},
    Category.C:  ALL_COMPUTER_TIERS,  # LLM-decided
    Category.D:  {DeviceTier.T3},
    Category.E:  {DeviceTier.T3},
    Category.F:  {DeviceTier.T3},
}

# Categories that may receive Mobile devices (phone / tablet / chromebook) too.
MOBILE_ELIGIBLE: set[Category] = {Category.D, Category.F}

# Categories explicitly NOT eligible for mobile-only allocations.
MOBILE_BLOCKED: set[Category] = {Category.E}


# Software keywords that require T2 or higher.
# Lowercased substring match against any string in `software_needed`.
HEAVY_SOFTWARE_T1 = {
    "vmware", "virtualbox", "vm ", "virtual machine",
    "docker", "kubernetes",
    "android studio", "xcode", "ios emulator",
    "tensorflow", "pytorch", "cuda", "ml framework",
    "premiere", "after effects", "davinci resolve",
    "blender", "maya", "3d render",
    "unreal engine", "unity 3d",
}

MEDIUM_SOFTWARE_T2 = {
    "photoshop", "illustrator", "indesign", "adobe",
    "autocad", "solidworks", "fusion 360",
    "matlab", "spss", "stata", "r studio", "rstudio",
    "intellij", "pycharm", "webstorm", "visual studio",
    "office", "excel", "powerpoint", "word",
    "zoom", "teams", "google meet",
}


def allowed_tiers(category: Category, intake: IntakeAnswers) -> set[DeviceTier]:
    """Return the allowed computer tier set for a category.

    For A3 (post-secondary), the sub-track narrows the set:
      - software_engineering with heavy software keywords -> all tiers
      - software_engineering otherwise                    -> {T2}
      - arts / science / business                         -> {T2}
      - unknown sub-track                                 -> {T2, T3}

    For C (employment), the engine still passes the full set down to the LLM,
    but if no LLM is available the deterministic fallback is {T2, T3}.
    """
    if category == Category.A3:
        return _a3_allowed(intake)
    if category == Category.C:
        return {DeviceTier.T2, DeviceTier.T3}
    return DIRECT_LINKING[category]


def _a3_allowed(intake: IntakeAnswers) -> set[DeviceTier]:
    track = intake.a3_subtrack
    software_blob = " ".join(intake.software_needed).lower()

    if track == A3Subtrack.SOFTWARE_ENGINEERING:
        if any(kw in software_blob for kw in HEAVY_SOFTWARE_T1):
            return {DeviceTier.T1, DeviceTier.T2}
        return {DeviceTier.T2}
    if track in {A3Subtrack.ARTS, A3Subtrack.SCIENCE, A3Subtrack.BUSINESS}:
        return {DeviceTier.T2}
    # Unknown / not yet parsed
    return {DeviceTier.T2, DeviceTier.T3}


def needed_tier(category: Category, intake: IntakeAnswers) -> DeviceTier:
    """Return the *primary* tier this applicant needs (used for efficiency).

    Picks the highest tier inside the allowed set, since efficiency penalises
    over-allocation — handing out a T1 when the applicant's allowed set is
    {T2, T3} should count as over-allocation relative to T2.
    """
    allowed = allowed_tiers(category, intake)
    if not allowed:
        return DeviceTier.T3
    # Pick the *most powerful* allowed tier as the "ceiling" of need.
    ranked = sorted(allowed, key=lambda t: {"T1": 3, "T2": 2, "T3": 1}[t.value], reverse=True)
    return ranked[0]


def device_meets_software(device_tier: DeviceTier | None, software_needed: list[str]) -> bool:
    """Return True if the device tier can plausibly run the requested software.

    Hard rule: T3 cannot run any heavy or medium-weight software.
    T2 can run medium but not heavy.
    T1 runs everything.
    None (non-computer device) returns True — software fit is judged elsewhere.
    """
    if device_tier is None or device_tier == DeviceTier.OTHER:
        return True
    blob = " ".join(software_needed).lower()
    if not blob.strip() or blob.strip() == "none":
        return True
    has_heavy = any(kw in blob for kw in HEAVY_SOFTWARE_T1)
    has_medium = any(kw in blob for kw in MEDIUM_SOFTWARE_T2)
    if device_tier == DeviceTier.T1:
        return True
    if device_tier == DeviceTier.T2:
        return not has_heavy
    # T3
    return not (has_heavy or has_medium)


def mobile_allowed(category: Category) -> bool:
    """Whether this category may receive a mobile device (phone / tablet)."""
    return category in MOBILE_ELIGIBLE


def mobile_blocked(category: Category) -> bool:
    return category in MOBILE_BLOCKED


def category_needs_computer(category: Category, intake: IntakeAnswers) -> bool:
    """Whether this application requires a computer.

    Used to gate the item_type. A senior or newcomer accepting a mobile-only
    allocation still passes the gate; categories with no mobile option require
    a computer.
    """
    # Senior or Newcomer with very light usage may be served by mobile.
    if category in MOBILE_ELIGIBLE:
        return False
    return True
