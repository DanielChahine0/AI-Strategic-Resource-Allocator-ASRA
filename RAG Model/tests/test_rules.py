"""Direct-linking rules and fit-gate tests."""
from __future__ import annotations

from datetime import date

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
