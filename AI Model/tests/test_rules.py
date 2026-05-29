"""Direct-linking rules and software-capability checks."""

from __future__ import annotations

import json
from pathlib import Path

from asra_matcher import rules
from asra_matcher.models import IntakeAnswers
from asra_matcher.taxonomy import A3Subtrack, Category, DeviceTier, Urgency


def _intake(**overrides) -> IntakeAnswers:
    defaults = dict(
        who_needs_it="x",
        main_usage=[],
        software_needed=[],
        shared_user_count=1,
        urgency=Urgency.MEDIUM,
        purpose=[Category.E],
    )
    defaults.update(overrides)
    return IntakeAnswers(**defaults)


# ---- Direct linking per category -----------------------------------------


def test_A1_only_T3():
    assert rules.allowed_tiers(Category.A1, _intake()) == {DeviceTier.T3}


def test_A2_only_T2():
    assert rules.allowed_tiers(Category.A2, _intake()) == {DeviceTier.T2}


def test_B_never_T1():
    allowed = rules.allowed_tiers(Category.B, _intake())
    assert DeviceTier.T1 not in allowed
    assert allowed == {DeviceTier.T2, DeviceTier.T3}


def test_D_only_T3():
    assert rules.allowed_tiers(Category.D, _intake()) == {DeviceTier.T3}


def test_E_only_T3():
    assert rules.allowed_tiers(Category.E, _intake()) == {DeviceTier.T3}


def test_F_only_T3():
    assert rules.allowed_tiers(Category.F, _intake()) == {DeviceTier.T3}


# ---- A3 sub-track behaviour ----------------------------------------------


def test_A3_software_engineering_with_VM_allows_T1():
    intake = _intake(
        a3_subtrack=A3Subtrack.SOFTWARE_ENGINEERING,
        software_needed=["Docker", "VirtualBox"],
    )
    allowed = rules.allowed_tiers(Category.A3, intake)
    assert DeviceTier.T1 in allowed
    assert DeviceTier.T2 in allowed


def test_A3_software_engineering_without_heavy_software_is_T2_only():
    intake = _intake(
        a3_subtrack=A3Subtrack.SOFTWARE_ENGINEERING,
        software_needed=["IntelliJ"],
    )
    allowed = rules.allowed_tiers(Category.A3, intake)
    assert allowed == {DeviceTier.T2}


def test_A3_arts_is_T2_only():
    intake = _intake(a3_subtrack=A3Subtrack.ARTS, software_needed=["Adobe Photoshop"])
    assert rules.allowed_tiers(Category.A3, intake) == {DeviceTier.T2}


def test_A3_unknown_subtrack_is_T2_T3():
    intake = _intake(a3_subtrack=None)
    assert rules.allowed_tiers(Category.A3, intake) == {DeviceTier.T2, DeviceTier.T3}


# ---- Mobile eligibility --------------------------------------------------


def test_D_and_F_can_get_mobile():
    assert rules.mobile_allowed(Category.D)
    assert rules.mobile_allowed(Category.F)


def test_E_cannot_get_mobile():
    assert rules.mobile_blocked(Category.E)


def test_other_categories_not_mobile_eligible():
    for c in [Category.A1, Category.A2, Category.A3, Category.B, Category.C]:
        assert not rules.mobile_allowed(c)


# ---- Software capability gate --------------------------------------------


def test_T3_cannot_run_photoshop():
    assert not rules.device_meets_software(DeviceTier.T3, ["Adobe Photoshop"])


def test_T3_can_run_browsing_only():
    assert rules.device_meets_software(DeviceTier.T3, [])
    assert rules.device_meets_software(DeviceTier.T3, ["none"])


def test_T2_cannot_run_VMs():
    assert not rules.device_meets_software(DeviceTier.T2, ["VirtualBox"])


def test_T2_can_run_photoshop():
    assert rules.device_meets_software(DeviceTier.T2, ["Adobe Photoshop"])


def test_T1_runs_everything():
    assert rules.device_meets_software(DeviceTier.T1, ["Docker", "Adobe Premiere"])


# ---- needed_tier ---------------------------------------------------------


def test_needed_tier_picks_ceiling_of_allowed_set():
    intake = _intake(a3_subtrack=A3Subtrack.SOFTWARE_ENGINEERING, software_needed=["Docker"])
    assert rules.needed_tier(Category.A3, intake) == DeviceTier.T1


def test_needed_tier_A1_is_T3():
    assert rules.needed_tier(Category.A1, _intake()) == DeviceTier.T3


# ---- Shared capability matrix (cross-engine agreement) -------------------


def _shared_matrix() -> dict[str, str]:
    path = Path(rules.__file__).resolve().parents[2] / "sample_data" / "software_capability_matrix.json"
    return json.loads(path.read_text())["software_min_tier"]


def test_software_matrix_loaded_from_shared_file():
    # The fit gate must be driven by the shared JSON, not the hard-coded fallback.
    assert rules._MATRIX_PATH.exists()
    assert rules.SOFTWARE_MIN_TIER == {
        k.lower(): DeviceTier(v) for k, v in _shared_matrix().items()
    }


def test_software_fit_matches_shared_matrix():
    """Every entry in the shared matrix runs on a device at its min tier and is
    rejected one tier below. This is the AI side of the 3-way agreement with the
    matrix and the RAG engine (which runs the same assertion against the same
    file), so the two fit gates cannot disagree."""
    rank = {"T1": 3, "T2": 2, "T3": 1}
    lower = {"T1": "T2", "T2": "T3"}
    for sw, min_t in _shared_matrix().items():
        assert rules.device_meets_software(DeviceTier(min_t), [sw]), f"{sw!r} must run on {min_t}"
        if rank[min_t] > 1:
            assert not rules.device_meets_software(DeviceTier(lower[min_t]), [sw]), (
                f"{sw!r} must NOT run on {lower[min_t]}"
            )


def test_reconciled_software_cases():
    # The specific cross-engine reconciliations from the audit.
    assert rules.device_meets_software(DeviceTier.T3, ["Microsoft Word"])   # Word -> T3
    assert rules.device_meets_software(DeviceTier.T3, ["Microsoft Office"])  # Office -> T3
    assert not rules.device_meets_software(DeviceTier.T2, ["Visual Studio"])  # full VS -> T1
    assert rules.device_meets_software(DeviceTier.T2, ["VS Code"])           # VS Code -> T2
    assert not rules.device_meets_software(DeviceTier.T3, ["Docker"])        # Docker -> T1
