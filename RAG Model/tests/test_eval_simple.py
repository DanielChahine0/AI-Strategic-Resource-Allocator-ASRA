"""Tests for the simplified impact harness (stubbed AI, fixed inventory)."""
from __future__ import annotations

from datetime import datetime

import pytest

from asra_matcher import eval_simple, llm
from asra_matcher.models import Device
from asra_matcher.taxonomy import DeviceTier, ItemType


@pytest.fixture(autouse=True)
def _stub_ai(monkeypatch):
    def fake(main_needs, software, challenge, devices):
        return ({d.id: {"needs_fit": 0.9, "challenge_fit": 0.8, "explanation": "ok"}
                 for d in devices}, True)
    monkeypatch.setattr(llm, "fit_and_explain", fake)


@pytest.fixture
def inv() -> list[Device]:
    return [
        Device(id="T1", item_type=ItemType.COMPUTER, tier=DeviceTier.T1,
               specs={"cpu": "AMD Ryzen 7", "ram_gb": 32}, condition=4,
               available_from=datetime(2026, 1, 1).date()),
        Device(id="T2", item_type=ItemType.COMPUTER, tier=DeviceTier.T2,
               specs={"cpu": "Intel Core i5 (10th Gen)", "ram_gb": 8}, condition=4,
               available_from=datetime(2026, 1, 1).date()),
    ]


def test_dataset_loads_and_has_etobicoke():
    everyone = eval_simple.load_applicants()
    etob = eval_simple.load_applicants("Etobicoke")
    assert len(everyone) >= 10
    assert 0 < len(etob) < len(everyone)
    assert all((a.area or "").lower() == "etobicoke" for a in etob)
    # The simplified dataset only carries the four intake answers.
    assert set(everyone[0].intake.model_dump()) == {"os_choice", "main_needs", "software", "challenge"}


def test_impact_report_for_etobicoke(inv):
    rep = eval_simple.run_impact("Etobicoke", inventory=inv)
    assert rep.area_filter == "Etobicoke"
    assert rep.applicants == rep.matched + rep.unmatched
    assert rep.applicants > 0
    assert 0.0 <= rep.match_rate <= 1.0
    assert rep.resolved_with_ai + rep.resolved_deterministically == rep.applicants
    assert rep.inventory_available == 2
    assert rep.batch.total == rep.applicants


def test_impact_all_areas(inv):
    rep = eval_simple.run_impact(None, inventory=inv)
    assert rep.area_filter is None
    assert len(rep.by_area) >= 2  # multiple GTA areas present
