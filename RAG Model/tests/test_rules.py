"""Direct-linking rules and fit-gate tests."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from asra_matcher import rules
from asra_matcher.models import Device
from asra_matcher.splitter import split
from asra_matcher.taxonomy import Category, DeviceTier, ItemType


def _device(item_type: ItemType, tier: DeviceTier | None = None) -> Device:
    return Device(
        id="X",
        item_type=item_type,
        tier=tier,
        specs={},
        condition=4,
        available_from=date(2026, 5, 12),
    )


def test_allowed_tiers_direct_linked(make_applicant):
    assert rules.allowed_tiers(Category.A1) == {DeviceTier.T3}
    assert rules.allowed_tiers(Category.A2) == {DeviceTier.T2}
    assert rules.allowed_tiers(Category.B) == {DeviceTier.T2, DeviceTier.T3}
    assert rules.allowed_tiers(Category.D) == {DeviceTier.T3}
    assert rules.allowed_tiers(Category.E) == {DeviceTier.T3}
    assert rules.allowed_tiers(Category.F) == {DeviceTier.T3}


def test_allowed_tiers_rag_decided():
    assert rules.allowed_tiers(Category.A3) is None
    assert rules.allowed_tiers(Category.C) is None


def test_fit_gate_A1_only_T3(make_applicant):
    app = split(make_applicant(Category.A1))[0]
    assert rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T3), app)
    assert not rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T2), app)
    assert not rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T1), app)


def test_fit_gate_A2_only_T2(make_applicant):
    app = split(make_applicant(Category.A2))[0]
    assert rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T2), app)
    assert not rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T1), app)
    assert not rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T3), app)


def test_fit_gate_B_never_T1(make_applicant):
    app = split(make_applicant(Category.B))[0]
    assert not rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T1), app)
    assert rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T2), app)
    assert rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T3), app)


def test_fit_gate_D_and_F_accept_mobile(make_applicant):
    for cat in (Category.D, Category.F):
        app = split(make_applicant(cat))[0]
        assert rules.fit_gate(_device(ItemType.MOBILE), app)
        assert rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T3), app)


def test_fit_gate_E_basic_only(make_applicant):
    app = split(make_applicant(Category.E))[0]
    assert rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T3), app)
    for t in (DeviceTier.T1, DeviceTier.T2):
        assert not rules.fit_gate(_device(ItemType.COMPUTER, t), app)
    # Peripherals never standalone.
    assert not rules.fit_gate(_device(ItemType.DISPLAY), app)


def test_fit_gate_rejects_peripheral(make_applicant):
    app = split(make_applicant(Category.A1))[0]
    assert not rules.fit_gate(_device(ItemType.INPUT), app)
    assert not rules.fit_gate(_device(ItemType.DISPLAY), app)


def test_fit_gate_A3_with_rag_narrowing(make_applicant):
    app = split(make_applicant(Category.A3))[0]
    # With RAG forcing only T2 allowed, T1 should be rejected.
    rag_allowed = {DeviceTier.T2}
    assert rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T2), app, rag_allowed_tiers=rag_allowed)
    assert not rules.fit_gate(_device(ItemType.COMPUTER, DeviceTier.T1), app, rag_allowed_tiers=rag_allowed)


def test_fit_gate_software_violates_tier(make_applicant):
    # Docker is T1; a T3 device should be rejected.
    app = split(
        make_applicant(Category.A3, software_needed=["Docker Desktop"])
    )[0]
    rag_allowed = {DeviceTier.T2, DeviceTier.T3}
    assert not rules.fit_gate(
        _device(ItemType.COMPUTER, DeviceTier.T3), app, rag_allowed_tiers=rag_allowed
    )


def test_software_violates_tier_handles_unknown():
    assert not rules.software_violates_tier(
        ["proprietary-app-xyz"], DeviceTier.T3
    )


def test_software_violates_tier_handles_none_string():
    assert not rules.software_violates_tier(["none", ""], DeviceTier.T3)


# ---- Shared capability matrix (cross-engine agreement) -------------------


def _shared_matrix() -> dict[str, str]:
    path = Path(rules.__file__).resolve().parents[2] / "sample_data" / "software_capability_matrix.json"
    return json.loads(path.read_text())["software_min_tier"]


def test_software_matrix_loaded_from_shared_file():
    # The fit gate must be driven by the shared JSON, not the hard-coded fallback.
    assert rules._MATRIX_PATH.exists()
    assert rules.DEFAULT_SOFTWARE_MIN_TIER == {
        k.lower(): DeviceTier(v) for k, v in _shared_matrix().items()
    }


def test_software_fit_matches_shared_matrix():
    """Every entry in the shared matrix runs on a device at its min tier and is
    rejected one tier below. This is the RAG side of the 3-way agreement with the
    matrix and the AI engine (which runs the same assertion against the same
    file), so the two fit gates cannot disagree."""
    rank = {"T1": 3, "T2": 2, "T3": 1}
    lower = {"T1": "T2", "T2": "T3"}
    for sw, min_t in _shared_matrix().items():
        assert not rules.software_violates_tier([sw], DeviceTier(min_t)), f"{sw!r} must run on {min_t}"
        if rank[min_t] > 1:
            assert rules.software_violates_tier([sw], DeviceTier(lower[min_t])), (
                f"{sw!r} must NOT run on {lower[min_t]}"
            )


def test_reconciled_software_cases():
    # The specific cross-engine reconciliations from the audit.
    assert not rules.software_violates_tier(["Microsoft Word"], DeviceTier.T3)   # Word -> T3
    assert not rules.software_violates_tier(["Microsoft Office"], DeviceTier.T3)  # Office -> T3
    assert rules.software_violates_tier(["Visual Studio"], DeviceTier.T2)         # full VS -> T1
    assert not rules.software_violates_tier(["VS Code"], DeviceTier.T2)           # VS Code -> T2
    assert rules.software_violates_tier(["Docker"], DeviceTier.T3)                # Docker -> T1
