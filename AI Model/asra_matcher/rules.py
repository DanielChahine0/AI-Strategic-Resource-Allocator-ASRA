"""Deterministic direct-linking rules from the LGT framework.

The LLM is consulted only for non-deterministic categories (A3, C). For
every other category, allowed tiers are fixed here.
"""

from __future__ import annotations

import json
from pathlib import Path

from asra_matcher.models import IntakeAnswers
from asra_matcher.taxonomy import A3Subtrack, Category, DeviceTier

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


# --- Software capability matrix -------------------------------------------
# Single source of truth shared with the RAG engine: sample_data/
# software_capability_matrix.json maps a software keyword to the minimum device
# tier that can run it. BOTH engines load that same file and use the identical
# matching rule in `required_software_tier`, so their fit gates agree on every
# (software, tier) pair. The hard-coded fallback mirrors the JSON and only kicks
# in if the file is missing.
_MATRIX_PATH = Path(__file__).resolve().parents[2] / "sample_data" / "software_capability_matrix.json"

_FALLBACK_SOFTWARE_MIN_TIER: dict[str, DeviceTier] = {
    "microsoft 365": DeviceTier.T3, "office 365": DeviceTier.T3,
    "microsoft office": DeviceTier.T3, "office": DeviceTier.T3,
    "word": DeviceTier.T3, "excel": DeviceTier.T3, "powerpoint": DeviceTier.T3,
    "google workspace": DeviceTier.T3, "google docs": DeviceTier.T3,
    "google meet": DeviceTier.T3, "zoom": DeviceTier.T3, "teams": DeviceTier.T3,
    "microsoft teams": DeviceTier.T3, "skype": DeviceTier.T3,
    "chrome": DeviceTier.T3, "firefox": DeviceTier.T3, "edge": DeviceTier.T3, "safari": DeviceTier.T3,
    "photoshop": DeviceTier.T2, "illustrator": DeviceTier.T2, "indesign": DeviceTier.T2,
    "adobe": DeviceTier.T2, "figma": DeviceTier.T2,
    "vs code": DeviceTier.T2, "visual studio code": DeviceTier.T2,
    "intellij": DeviceTier.T2, "pycharm": DeviceTier.T2, "webstorm": DeviceTier.T2,
    "matlab": DeviceTier.T2, "rstudio": DeviceTier.T2, "r studio": DeviceTier.T2,
    "jupyter": DeviceTier.T2, "autocad": DeviceTier.T2, "solidworks": DeviceTier.T2,
    "fusion 360": DeviceTier.T2,
    "premiere": DeviceTier.T1, "premiere pro": DeviceTier.T1, "after effects": DeviceTier.T1,
    "final cut": DeviceTier.T1, "davinci resolve": DeviceTier.T1,
    "android studio": DeviceTier.T1, "xcode": DeviceTier.T1,
    "docker": DeviceTier.T1, "docker desktop": DeviceTier.T1,
    "virtualbox": DeviceTier.T1, "vmware": DeviceTier.T1, "vm": DeviceTier.T1, "vms": DeviceTier.T1,
    "virtual machine": DeviceTier.T1, "kubernetes": DeviceTier.T1, "visual studio": DeviceTier.T1,
    "unity": DeviceTier.T1, "unreal": DeviceTier.T1, "unreal engine": DeviceTier.T1,
    "pytorch": DeviceTier.T1, "tensorflow": DeviceTier.T1, "cuda": DeviceTier.T1,
    "blender": DeviceTier.T1, "maya": DeviceTier.T1, "3d render": DeviceTier.T1,
}


def _load_software_min_tier() -> dict[str, DeviceTier]:
    try:
        raw = json.loads(_MATRIX_PATH.read_text())
        table = {
            str(k).strip().lower(): DeviceTier(str(v))
            for k, v in raw["software_min_tier"].items()
        }
        if table:
            return table
    except Exception:
        pass
    return dict(_FALLBACK_SOFTWARE_MIN_TIER)


SOFTWARE_MIN_TIER: dict[str, DeviceTier] = _load_software_min_tier()

_TIER_RANK = {DeviceTier.T1: 3, DeviceTier.T2: 2, DeviceTier.T3: 1, DeviceTier.OTHER: 0}


def required_software_tier(software_needed: list[str]) -> DeviceTier:
    """Minimum device tier that can run *all* the requested software.

    For each item, the longest matrix key that is a substring of the item wins
    (so "visual studio code" -> T2, not the shorter "visual studio" -> T1); the
    result is the highest tier any single item requires. Items absent from the
    matrix add no constraint. The RAG engine carries the identical algorithm so
    the two fit gates never disagree.
    """
    required = DeviceTier.T3
    for s in software_needed:
        key = s.strip().lower()
        if not key or key == "none":
            continue
        best: DeviceTier | None = None
        best_len = -1
        for mk, mv in SOFTWARE_MIN_TIER.items():
            if mk in key and len(mk) > best_len:
                best, best_len = mv, len(mk)
        if best is not None and _TIER_RANK[best] > _TIER_RANK[required]:
            required = best
    return required


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

    if track == A3Subtrack.SOFTWARE_ENGINEERING:
        if required_software_tier(intake.software_needed) == DeviceTier.T1:
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

    A computer tier passes iff it is at least the minimum tier the software
    requires (see `required_software_tier`, shared with the RAG engine). A None
    or OTHER tier (non-computer device) returns True — software fit for those is
    judged elsewhere.
    """
    if device_tier is None or device_tier == DeviceTier.OTHER:
        return True
    return _TIER_RANK[device_tier] >= _TIER_RANK[required_software_tier(software_needed)]


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
