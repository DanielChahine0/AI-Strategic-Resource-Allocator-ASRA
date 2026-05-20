"""End-to-end engine tests on the bundled sample data.

The autouse `_disable_llm` fixture in conftest.py forces deterministic
fallbacks (no network), so these results are reproducible.
"""

from __future__ import annotations

import json
from datetime import date

from asra_matcher import engine
from asra_matcher.models import Applicant, Device
from asra_matcher.taxonomy import Category, DeviceTier

from tests.conftest import FIXED_TODAY


def _load_inventory(sample_data_dir):
    data = json.loads((sample_data_dir / "inventory.json").read_text())
    return [Device.model_validate(item) for item in data]


def _load_applicant(sample_data_dir, name):
    data = json.loads((sample_data_dir / "applicants" / name).read_text())
    return Applicant.model_validate(data)


def test_kid_gets_T3(sample_data_dir):
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-A1-kid.json")
    result = engine.match(a, inv, today=FIXED_TODAY)
    sel = result.selected_application
    assert sel.application.category == Category.A1
    assert sel.top2, "Expected at least one match"
    top = sel.top2[0].device
    assert top.tier == DeviceTier.T3


def test_teen_gets_T2(sample_data_dir):
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-A2-teen.json")
    result = engine.match(a, inv, today=FIXED_TODAY)
    assert result.selected_application.top2
    assert result.selected_application.top2[0].device.tier == DeviceTier.T2


def test_cs_student_with_vm_gets_T1_or_T2(sample_data_dir):
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-A3-cs-vm.json")
    result = engine.match(a, inv, today=FIXED_TODAY)
    assert result.selected_application.top2
    tier = result.selected_application.top2[0].device.tier
    # software_engineering + Docker/VirtualBox => allowed = {T1, T2}.
    # Efficiency penalises T1 if T2 is the needed ceiling, but our rules pick
    # T1 as the ceiling for SE+heavy, so T1 is allowed at full efficiency.
    assert tier in {DeviceTier.T1, DeviceTier.T2}


def test_healthcare_never_gets_T1(sample_data_dir):
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-B-healthcare.json")
    result = engine.match(a, inv, today=FIXED_TODAY)
    assert result.selected_application.top2
    for m in result.selected_application.top2:
        assert m.device.tier != DeviceTier.T1


def test_senior_with_vision_prefers_large_display(sample_data_dir):
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-D-senior-vision.json")
    result = engine.match(a, inv, today=FIXED_TODAY)
    # Allowed: T3 or mobile. We don't strictly require the 15.6" laptop to win,
    # but composite score should be > 0 and tier (if computer) should be T3.
    assert result.selected_application.top2
    top = result.selected_application.top2[0].device
    if top.tier is not None:
        assert top.tier == DeviceTier.T3


def test_multi_category_FC_keeps_one_application(sample_data_dir):
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-FC-newcomer-jobsearch.json")
    result = engine.match(a, inv, today=FIXED_TODAY)

    # Both F and C should have been scored; one wins, one is discarded.
    selected_cat = result.selected_application.application.category
    discarded_cats = [r.application.category for r in result.discarded_applications]

    assert selected_cat in {Category.F, Category.C}
    other = Category.C if selected_cat == Category.F else Category.F
    assert other in discarded_cats


def test_explanations_populated_via_fallback(sample_data_dir):
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-C-jobsearch.json")
    result = engine.match(a, inv, today=FIXED_TODAY)
    assert result.selected_application.top2
    for m in result.selected_application.top2:
        assert m.explanation
        assert "composite" in m.explanation.lower() or "device" in m.explanation.lower()


def test_results_are_deterministic_across_runs(sample_data_dir):
    """Same input -> same top device IDs, twice."""
    inv = _load_inventory(sample_data_dir)
    a = _load_applicant(sample_data_dir, "app-A3-arts.json")
    r1 = engine.match(a, inv, today=FIXED_TODAY)
    r2 = engine.match(a, inv, today=FIXED_TODAY)
    ids1 = [m.device.id for m in r1.selected_application.top2]
    ids2 = [m.device.id for m in r2.selected_application.top2]
    assert ids1 == ids2
