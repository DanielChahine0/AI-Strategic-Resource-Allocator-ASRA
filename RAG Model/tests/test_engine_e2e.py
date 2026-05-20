"""End-to-end engine tests with retrieval and LLM calls mocked."""
from __future__ import annotations

from datetime import date

from asra_matcher import engine as engine_mod
from asra_matcher.llm import MatchExplanation, TierRecommendation
from asra_matcher.splitter import split
from asra_matcher.taxonomy import Category, DeviceTier, Urgency


def _no_op_explainer(app, devices):
    return MatchExplanation(
        explanations={d.id: f"explanation for {d.id}" for d in devices},
        citations={d.id: ["fake_source.md"] for d in devices},
        chunks=[],
    )


def _stub_recommender(tier: DeviceTier):
    def _r(app):
        return TierRecommendation(
            recommended_tier=tier,
            rationale="stub",
            citations=[],
            confidence=0.9,
            chunks=[],
        )
    return _r


def test_engine_A1_picks_T3(make_applicant, sample_inventory):
    applicant = make_applicant(Category.A1, urgency=Urgency.CRITICAL)
    result = engine_mod.match(
        applicant,
        sample_inventory,
        today=date(2026, 5, 12),
        tier_recommender=_stub_recommender(DeviceTier.T3),
        explainer=_no_op_explainer,
    )
    assert result.top_matches
    top = result.top_matches[0]
    assert top.device.tier == DeviceTier.T3


def test_engine_A3_swe_with_docker_steps_up_to_T1(make_applicant, sample_inventory):
    applicant = make_applicant(
        Category.A3,
        urgency=Urgency.HIGH,
        software_needed=["Docker Desktop", "VS Code"],
    )
    result = engine_mod.match(
        applicant,
        sample_inventory,
        today=date(2026, 5, 12),
        tier_recommender=_stub_recommender(DeviceTier.T1),
        explainer=_no_op_explainer,
    )
    # With Docker in software_needed and RAG recommending T1, the engine should
    # land on a T1 (the fit gate rejected T2 and T3 because of Docker).
    assert result.top_matches
    top = result.top_matches[0]
    assert top.device.tier == DeviceTier.T1


def test_engine_multi_category_picks_best(make_applicant, sample_inventory):
    # Use HIGH (not CRITICAL) urgency so the priority bump differentiates.
    # CRITICAL+any bumps already clamp at 1.0 → F and C tie.
    applicant = make_applicant(Category.F, urgency=Urgency.HIGH)
    applicant.intake.purpose = [Category.F, Category.C]
    result = engine_mod.match(
        applicant,
        sample_inventory,
        today=date(2026, 5, 12),
        tier_recommender=_stub_recommender(DeviceTier.T3),
        explainer=_no_op_explainer,
    )
    # Both F and C top out on the same T3 device, but C earns the +0.05 priority
    # bump so the engine should select the C application.
    assert result.chosen_application.category == Category.C
    assert any(
        a.category == Category.F for a in result.discarded_applications
    )


def test_engine_no_devices_returns_empty(make_applicant):
    applicant = make_applicant(Category.A1)
    result = engine_mod.match(
        applicant,
        [],
        today=date(2026, 5, 12),
        tier_recommender=_stub_recommender(DeviceTier.T3),
        explainer=_no_op_explainer,
    )
    assert result.top_matches == []
    assert any("no devices" in n.lower() for n in result.notes)


def test_engine_returns_top_2(make_applicant, sample_inventory):
    applicant = make_applicant(Category.E, urgency=Urgency.MEDIUM)
    result = engine_mod.match(
        applicant,
        sample_inventory,
        today=date(2026, 5, 12),
        tier_recommender=_stub_recommender(DeviceTier.T3),
        explainer=_no_op_explainer,
    )
    # E only accepts T3, and sample_inventory has 2 T3 computers.
    assert len(result.top_matches) == 2
    assert all(m.device.tier == DeviceTier.T3 for m in result.top_matches)
