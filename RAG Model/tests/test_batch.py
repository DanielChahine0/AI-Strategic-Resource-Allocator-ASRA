"""Tests for the FCFS batch runner (stubbed AI call, fixed inventory)."""
from __future__ import annotations

from datetime import datetime

import pytest

from asra_matcher import batch, llm, simple
from asra_matcher.models import Device
from asra_matcher.taxonomy import DeviceTier, ItemType, OSChoice


@pytest.fixture(autouse=True)
def _stub_ai(monkeypatch):
    def fake(main_needs, software, challenge, devices):
        return ({d.id: {"needs_fit": 0.9, "challenge_fit": 0.8, "explanation": "ok"}
                 for d in devices}, True)
    monkeypatch.setattr(llm, "fit_and_explain", fake)


@pytest.fixture
def inv() -> list[Device]:
    return [
        Device(id="NEW-T2", item_type=ItemType.COMPUTER, tier=DeviceTier.T2,
               specs={"cpu": "Intel Core i5 (10th Gen)", "ram_gb": 8}, condition=4,
               available_from=datetime(2026, 1, 1).date()),
        Device(id="NEW-T1", item_type=ItemType.COMPUTER, tier=DeviceTier.T1,
               specs={"cpu": "AMD Ryzen 7", "ram_gb": 32}, condition=4,
               available_from=datetime(2026, 1, 1).date()),
    ]


def _app(aid: str, area: str, day: int) -> simple.SimpleApplicant:
    return simple.SimpleApplicant(
        applicant_id=aid, area=area,
        submitted_at=datetime(2026, 3, day),
        intake=simple.SimpleIntake(os_choice=OSChoice.UBUNTU, main_needs="x", software="Chrome", challenge="y"),
    )


def test_batch_groups_by_area_and_counts(inv):
    apps = [_app("a1", "Etobicoke", 3), _app("b1", "Scarborough", 1), _app("a2", "Etobicoke", 1)]
    res = batch.run_batch(apps, inv, group_by="area", batch_size=2)
    assert res.total == 3
    assert res.groups == {"Etobicoke": 2, "Scarborough": 1}
    assert res.used_ai_count == 3
    assert res.unmatched_count == 0
    assert all(it.matched_device_id for it in res.items)


def test_batch_fcfs_order_within_group(inv):
    apps = [_app("late", "Etobicoke", 9), _app("early", "Etobicoke", 1)]
    res = batch.run_batch(apps, inv, group_by="area")
    ids = [it.applicant_id for it in res.items]
    assert ids == ["early", "late"]  # earliest submission first


def test_batch_reports_unmatched(monkeypatch, inv):
    # An applicant wanting Windows on a pool with only an old (Ubuntu-only) CPU.
    old = [Device(id="OLD", item_type=ItemType.COMPUTER, tier=DeviceTier.T1,
                  specs={"cpu": "Intel Core i7 (4th Gen)", "ram_gb": 4}, condition=4,
                  available_from=datetime(2026, 1, 1).date())]
    app = simple.SimpleApplicant(
        applicant_id="w", intake=simple.SimpleIntake(os_choice=OSChoice.WINDOWS))
    res = batch.run_batch([app], old, group_by="none")
    assert res.unmatched_count == 1
    assert res.items[0].matched_device_id is None
