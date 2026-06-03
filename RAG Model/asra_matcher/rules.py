"""Deterministic software-capability matrix (shared with the AI engine).

Maps a software keyword to the minimum device tier that can run it, sourced from
the shared sample_data/software_capability_matrix.json with a hard-coded
fallback. The category/tier direct-linking rules and fit gate were removed in
the Phase-5 simplification — the simplified allocator's only hard rule is the
software-capability check in `asra_matcher.simple`.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .taxonomy import DeviceTier

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


DEFAULT_SOFTWARE_MIN_TIER: dict[str, DeviceTier] = _load_software_min_tier()


def _tier_rank(t: DeviceTier) -> int:
    return {DeviceTier.T1: 3, DeviceTier.T2: 2, DeviceTier.T3: 1, DeviceTier.OTHER: 0}[t]


def _required_tier(software_needed: Iterable[str], table: dict[str, DeviceTier]) -> DeviceTier:
    """Minimum device tier that can run *all* the requested software.

    For each item, the longest matrix key that is a substring of the item wins
    (so "visual studio code" -> T2, not the shorter "visual studio" -> T1); the
    result is the highest tier any single item requires. Items absent from the
    matrix add no constraint.
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
