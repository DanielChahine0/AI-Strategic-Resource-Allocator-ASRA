"""Tests for the simplified Q1–Q4 FCFS allocator (asra_matcher.simple).

Hermetic: the single AI call is stubbed, so nothing hits the network or quota.
"""
from __future__ import annotations

from datetime import date

import pytest

from asra_matcher import llm, simple
from asra_matcher.models import Device
from asra_matcher.taxonomy import DeviceTier, ItemType, OSChoice


def _dev(dev_id: str, tier: DeviceTier, *, cpu: str, ram: int | None, cond: int = 4) -> Device:
    specs: dict = {"cpu": cpu, "form_factor": "laptop"}
    if ram is not None:
        specs["ram_gb"] = ram
    return Device(
        id=dev_id, item_type=ItemType.COMPUTER, tier=tier, specs=specs,
        condition=cond, available_from=date(2026, 1, 1),
    )


# --- Q1 OS-capability filter ----------------------------------------------


def test_ubuntu_accepts_old_cpu_windows_rejects():
    old = _dev("OLD", DeviceTier.T1, cpu="Intel Core i7 (4th Gen)", ram=8)
    assert simple.os_capable(old, OSChoice.UBUNTU) is True
    assert simple.os_capable(old, OSChoice.WINDOWS) is False  # 4th gen < gen 8 bar
    assert simple.os_capable(old, OSChoice.BOTH) is False     # "both" = Windows bar


def test_windows_accepts_recent_intel_and_ryzen():
    new = _dev("NEW", DeviceTier.T2, cpu="Intel Core i5 (10th Gen)", ram=8)
    ryzen = _dev("RZ", DeviceTier.T2, cpu="AMD Ryzen 5 (5000 Series)", ram=8)
    assert simple.os_capable(new, OSChoice.WINDOWS) is True
    assert simple.os_capable(ryzen, OSChoice.WINDOWS) is True


def test_windows_rejects_low_ram_even_on_new_cpu():
    weak = _dev("WEAK", DeviceTier.T3, cpu="Intel Core i5 (10th Gen)", ram=4)
    assert simple.os_capable(weak, OSChoice.WINDOWS) is False
    assert simple.os_capable(weak, OSChoice.UBUNTU) is True  # 4GB clears Ubuntu bar


# --- Q3 deterministic software check --------------------------------------


def test_parse_software_splits_and_drops_none():
    assert simple.parse_software("Word, Excel; Zoom / Chrome and Docker") == [
        "Word", "Excel", "Zoom", "Chrome", "Docker",
    ]
    assert simple.parse_software("none") == []
    assert simple.parse_software("") == []


def test_software_assessment_blocks_low_tier_for_heavy_software():
    heavy = ["Docker", "Android Studio"]  # require T1 in the shared matrix
    t3 = _dev("T3", DeviceTier.T3, cpu="i3", ram=8)
    t1 = _dev("T1", DeviceTier.T1, cpu="i7", ram=32)
    ok_t3, fit_t3, notes = simple.software_assessment(t3, heavy)
    ok_t1, fit_t1, _ = simple.software_assessment(t1, heavy)
    assert ok_t3 is False and fit_t3 < 1.0 and notes
    assert ok_t1 is True and fit_t1 == 1.0


# --- Full pipeline (stubbed AI) -------------------------------------------


@pytest.fixture
def inv() -> list[Device]:
    return [
        _dev("OLD-T1", DeviceTier.T1, cpu="Intel Core i7 (4th Gen)", ram=8, cond=5),
        _dev("NEW-T2", DeviceTier.T2, cpu="Intel Core i5 (10th Gen)", ram=8, cond=3),
        _dev("NEW-T1", DeviceTier.T1, cpu="AMD Ryzen 7", ram=32, cond=4),
    ]


def _stub_fit(monkeypatch, *, used_ai=True):
    def fake(main_needs, software, challenge, devices):
        return ({d.id: {"needs_fit": 0.9, "challenge_fit": 0.8, "explanation": f"ok {d.id}"}
                 for d in devices}, used_ai)
    monkeypatch.setattr(llm, "fit_and_explain", fake)


def test_allocate_windows_excludes_old_cpu(monkeypatch, inv):
    _stub_fit(monkeypatch)
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(
            os_choice=OSChoice.WINDOWS, main_needs="office", software="Word", challenge="none"))
    res = simple.allocate(app, inv)
    assert res.after_os_filter == 2  # OLD-T1 (4th gen) excluded
    assert "OLD-T1" not in {m.device.id for m in res.top}
    assert res.used_ai is True
    assert all(0.0 <= m.score.composite <= 1.0 for m in res.top)


def test_allocate_no_capable_device_returns_empty(monkeypatch):
    _stub_fit(monkeypatch)
    only_old = [_dev("OLD", DeviceTier.T1, cpu="Intel Core i7 (4th Gen)", ram=4)]
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(os_choice=OSChoice.WINDOWS))
    res = simple.allocate(app, only_old)
    assert res.top == [] and res.after_os_filter == 0 and res.notes


def test_token_steps_are_recorded(monkeypatch, inv):
    _stub_fit(monkeypatch)
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(
            os_choice=OSChoice.UBUNTU, main_needs="x", software="Word", challenge="y"))
    res = simple.allocate(app, inv)
    names = [s.step for s in res.token_steps]
    assert names == ["os_filter", "software_check", "prerank", "fit_explain"]
    # Deterministic steps cost nothing; cumulative is monotonic.
    det = {s.step: s for s in res.token_steps if s.step != "fit_explain"}
    assert all(s.kind == "algorithm" and s.total_tokens == 0 for s in det.values())
    cums = [s.cumulative_total for s in res.token_steps]
    assert cums == sorted(cums)
    assert res.tokens_total == res.token_steps[-1].cumulative_total


def test_token_steps_present_when_os_filter_empty(monkeypatch):
    _stub_fit(monkeypatch)
    only_old = [_dev("OLD", DeviceTier.T1, cpu="Intel Core i7 (4th Gen)", ram=4)]
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(os_choice=OSChoice.WINDOWS))
    res = simple.allocate(app, only_old)
    assert [s.step for s in res.token_steps] == ["os_filter"]
    assert res.tokens_total == 0


def test_allocate_offline_fallback_still_ranks(monkeypatch, inv):
    _stub_fit(monkeypatch, used_ai=False)
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(
            os_choice=OSChoice.UBUNTU, main_needs="browsing", software="Chrome", challenge="no device"))
    res = simple.allocate(app, inv)
    assert res.used_ai is False
    assert len(res.top) == 2
    assert any("without the language model" in n for n in res.notes)
