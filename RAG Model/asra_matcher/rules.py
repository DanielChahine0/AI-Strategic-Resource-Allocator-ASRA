"""Direct-linking rules and fit gate. Deterministic; the LLM cannot override these."""
from __future__ import annotations

from collections.abc import Iterable

from .models import Application, Device
from .taxonomy import PERIPHERAL_TYPES, Category, DeviceTier, ItemType

# Default software → minimum tier mapping. Re-loaded at runtime from
# kb/software_capability_matrix.md if available; this hard-coded fallback keeps
# the fit gate working when the KB has not been ingested yet.
DEFAULT_SOFTWARE_MIN_TIER: dict[str, DeviceTier] = {
    "photoshop": DeviceTier.T2,
    "illustrator": DeviceTier.T2,
    "premiere": DeviceTier.T1,
    "premiere pro": DeviceTier.T1,
    "after effects": DeviceTier.T1,
    "final cut": DeviceTier.T1,
    "davinci resolve": DeviceTier.T1,
    "vs code": DeviceTier.T2,
    "visual studio code": DeviceTier.T2,
    "visual studio": DeviceTier.T1,
    "docker": DeviceTier.T1,
    "docker desktop": DeviceTier.T1,
    "android studio": DeviceTier.T1,
    "xcode": DeviceTier.T1,
    "unity": DeviceTier.T1,
    "unreal": DeviceTier.T1,
    "matlab": DeviceTier.T2,
    "rstudio": DeviceTier.T2,
    "jupyter": DeviceTier.T2,
    "pytorch": DeviceTier.T1,
    "tensorflow": DeviceTier.T1,
    "vm": DeviceTier.T1,
    "vms": DeviceTier.T1,
    "virtualbox": DeviceTier.T1,
    "vmware": DeviceTier.T1,
    "microsoft 365": DeviceTier.T3,
    "office 365": DeviceTier.T3,
    "word": DeviceTier.T3,
    "excel": DeviceTier.T3,
    "powerpoint": DeviceTier.T3,
    "google docs": DeviceTier.T3,
    "google workspace": DeviceTier.T3,
    "zoom": DeviceTier.T3,
    "teams": DeviceTier.T3,
    "google meet": DeviceTier.T3,
    "chrome": DeviceTier.T3,
    "firefox": DeviceTier.T3,
}


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


def software_violates_tier(
    software_needed: Iterable[str],
    device_tier: DeviceTier | None,
    software_min_tier: dict[str, DeviceTier] | None = None,
) -> bool:
    """True if any requested software exceeds the device's tier capability."""
    if device_tier is None or device_tier == DeviceTier.OTHER:
        return False  # peripheral / unknown; software gating doesn't apply here
    table = software_min_tier or DEFAULT_SOFTWARE_MIN_TIER
    dev_rank = _tier_rank(device_tier)
    for s in software_needed:
        key = s.strip().lower()
        if not key or key == "none":
            continue
        min_tier = table.get(key)
        if min_tier is None:
            # try a loose match: any matrix key contained in the software string
            for mk, mv in table.items():
                if mk in key:
                    min_tier = mv
                    break
        if min_tier is None:
            continue
        if dev_rank < _tier_rank(min_tier):
            return True
    return False


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
