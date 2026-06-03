"""Tests for the simplified Q1–Q4 FCFS allocator (asra_matcher.simple, RAG variant).

Hermetic: the single grounded AI call is stubbed, so nothing hits the network,
the vector store, or quota.
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


def test_os_filter_ubuntu_vs_windows():
    old = _dev("OLD", DeviceTier.T1, cpu="Intel Core i7 (4th Gen)", ram=8)
    new = _dev("NEW", DeviceTier.T2, cpu="Intel Core i5 (10th Gen)", ram=8)
    assert simple.os_capable(old, OSChoice.UBUNTU) is True
    assert simple.os_capable(old, OSChoice.WINDOWS) is False
    assert simple.os_capable(new, OSChoice.WINDOWS) is True


def test_parse_software_and_assessment():
    assert simple.parse_software("Word, Docker and Python") == ["Word", "Docker", "Python"]
    heavy = ["Docker"]
    t3 = _dev("T3", DeviceTier.T3, cpu="i3", ram=8)
    ok, fit, notes = simple.software_assessment(t3, heavy)
    assert ok is False and fit < 1.0 and notes


@pytest.fixture
def inv() -> list[Device]:
    return [
        _dev("OLD-T1", DeviceTier.T1, cpu="Intel Core i7 (4th Gen)", ram=8, cond=5),
        _dev("NEW-T2", DeviceTier.T2, cpu="Intel Core i5 (10th Gen)", ram=8, cond=3),
        _dev("NEW-T1", DeviceTier.T1, cpu="AMD Ryzen 7", ram=32, cond=4),
    ]


def _stub_fit(monkeypatch, *, used_ai=True):
    def fake(main_needs, software, challenge, devices):
        return ({d.id: {"needs_fit": 0.9, "challenge_fit": 0.8,
                        "explanation": f"ok {d.id}", "citations": ["tiers/T1.md"]}
                 for d in devices}, used_ai)
    monkeypatch.setattr(llm, "fit_and_explain", fake)


def test_allocate_carries_citations(monkeypatch, inv):
    _stub_fit(monkeypatch)
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(
            os_choice=OSChoice.UBUNTU, main_needs="dev", software="Docker", challenge="old phone"))
    res = simple.allocate(app, inv)
    assert res.used_ai is True
    assert res.top and res.top[0].citations == ["tiers/T1.md"]


def test_allocate_windows_excludes_old_cpu(monkeypatch, inv):
    _stub_fit(monkeypatch)
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(
            os_choice=OSChoice.WINDOWS, main_needs="office", software="Word", challenge="none"))
    res = simple.allocate(app, inv)
    assert res.after_os_filter == 2
    assert "OLD-T1" not in {m.device.id for m in res.top}


def test_token_steps_are_recorded(monkeypatch, inv):
    _stub_fit(monkeypatch)
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(
            os_choice=OSChoice.UBUNTU, main_needs="x", software="Word", challenge="y"))
    res = simple.allocate(app, inv)
    assert [s.step for s in res.token_steps] == ["os_filter", "software_check", "prerank", "fit_explain"]
    det = [s for s in res.token_steps if s.step != "fit_explain"]
    assert all(s.kind == "algorithm" and s.total_tokens == 0 for s in det)
    assert res.tokens_total == res.token_steps[-1].cumulative_total


def test_allocate_offline_fallback(monkeypatch, inv):
    _stub_fit(monkeypatch, used_ai=False)
    app = simple.SimpleApplicant(
        applicant_id="a", intake=simple.SimpleIntake(os_choice=OSChoice.UBUNTU))
    res = simple.allocate(app, inv)
    assert res.used_ai is False and len(res.top) == 2
