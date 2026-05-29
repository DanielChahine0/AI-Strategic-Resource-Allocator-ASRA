"""Direct-linking rules and fit gate. Deterministic; the LLM cannot override these."""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .models import Application, Device
from .taxonomy import PERIPHERAL_TYPES, Category, DeviceTier, ItemType

# --- Software capability matrix -------------------------------------------
# Single source of truth shared with the AI engine: sample_data/
# software_capability_matrix.json maps a software keyword to the minimum device
# tier that can run it. BOTH engines load that same file and use the identical
# longest-match rule in `_required_tier`, so their fit gates agree on every
# (software, tier) pair. The hard-coded fallback mirrors the JSON and only
# applies if the file is missing. (The human-readable kb/software_capability_
# matrix.md tracks the same data for retrieval/justification.)
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


# Public name kept for back-compat; now sourced from the shared matrix file.
DEFAULT_SOFTWARE_MIN_TIER: dict[str, DeviceTier] = _load_software_min_tier()


# Direct-linking allowed tier sets, per spec. None entries mean "RAG decides".
_ALLOWED_TIERS: dict[Category, set[DeviceTier] | None] = {
    Category.A1: {DeviceTier.T3},
    Category.A2: {DeviceTier.T2},
    Category.A3: None,  # RAG-decided based on sub-track + software
    Category.B: {DeviceTier.T2, DeviceTier.T3},
    Category.C: None,   # RAG-decided
    Category.D: {DeviceTier.T3},  # mobile handled separately via item_type
    Category.E: {DeviceTier.T3},
    Category.F: {DeviceTier.T3},  # mobile handled separately via item_type
}


# Categories where Mobile items are an acceptable alternative to a tiered computer.
_MOBILE_ELIGIBLE = {Category.D, Category.F}


def allowed_tiers(category: Category) -> set[DeviceTier] | None:
    """Return the direct-linking allowed tier set, or None if RAG must decide."""
    return _ALLOWED_TIERS[category]


def mobile_eligible(category: Category) -> bool:
    return category in _MOBILE_ELIGIBLE


def _tier_rank(t: DeviceTier) -> int:
    return {DeviceTier.T1: 3, DeviceTier.T2: 2, DeviceTier.T3: 1, DeviceTier.OTHER: 0}[t]


def _required_tier(
    software_needed: Iterable[str], table: dict[str, DeviceTier]
) -> DeviceTier:
    """Minimum device tier that can run *all* the requested software.

    For each item, the longest matrix key that is a substring of the item wins
    (so "visual studio code" -> T2, not the shorter "visual studio" -> T1); the
    result is the highest tier any single item requires. Items absent from the
    matrix add no constraint. The AI engine carries the identical algorithm
    (rules.required_software_tier) so the two fit gates never disagree.
    """
    required = DeviceTier.T3
    for s in software_needed:
        key = s.strip().lower()
        if not key or key == "none":
            continue
        best: DeviceTier | None = None
        best_len = -1
        for mk, mv in table.items():
            if mk in key and len(mk) > best_len:
                best, best_len = mv, len(mk)
        if best is not None and _tier_rank(best) > _tier_rank(required):
            required = best
    return required


def software_violates_tier(
    software_needed: Iterable[str],
    device_tier: DeviceTier | None,
    software_min_tier: dict[str, DeviceTier] | None = None,
) -> bool:
    """True if any requested software exceeds the device's tier capability.

    Uses the shared capability matrix and the identical longest-match rule as
    the AI engine, so the two fit gates agree on every (software, tier) pair.
    """
    if device_tier is None or device_tier == DeviceTier.OTHER:
        return False  # peripheral / unknown; software gating doesn't apply here
    table = software_min_tier or DEFAULT_SOFTWARE_MIN_TIER
    required = _required_tier(software_needed, table)
    return _tier_rank(device_tier) < _tier_rank(required)


def fit_gate(
    device: Device,
    application: Application,
    *,
    rag_allowed_tiers: set[DeviceTier] | None = None,
    software_min_tier: dict[str, DeviceTier] | None = None,
) -> bool:
    """Hard fit gate. Returns False if the device cannot serve this application.

    `rag_allowed_tiers` narrows the candidate tier set for categories where the
    rules layer defers to RAG (A3, C). When provided, it intersects with the
    rule-level allowed set.
    """
    category = application.category
    rule_set = allowed_tiers(category)

    if device.item_type == ItemType.MOBILE:
        return mobile_eligible(category)

    if device.item_type in PERIPHERAL_TYPES:
        # Peripherals are not standalone matches in the MVP. They could be
        # bundled later, but the fit gate blocks them here.
        return False

    if device.item_type != ItemType.COMPUTER:
        return False

    if device.tier is None or device.tier == DeviceTier.OTHER:
        return False

    candidate_tiers = rule_set if rule_set is not None else set(DeviceTier) - {DeviceTier.OTHER}
    if rag_allowed_tiers is not None:
        candidate_tiers = candidate_tiers & rag_allowed_tiers
    if device.tier not in candidate_tiers:
        return False

    if software_violates_tier(
        application.intake.software_needed, device.tier, software_min_tier
    ):
        return False

    return True
