"""Tests for the evaluation-run mode.

The autouse `_disable_llm` fixture (conftest.py) forces deterministic fallbacks,
so every run here is offline and reproducible: token counts are 0 and
`fallback_used` is True, while accuracy / confidence / explanation-quality are
all computed from the deterministic pipeline output.
"""

from __future__ import annotations

from asra_matcher import eval as eval_mod

# ----- scorers -----------------------------------------------------------


def test_score_accuracy_category_and_tier():
    truth = {"category": "A3", "tier": "T1", "acceptable_tiers": ["T1"]}
    acc = eval_mod.score_accuracy("A3", "T1", "DEV-1", truth)
    assert acc.category_correct and acc.tier_correct
    assert acc.score == 1.0

    half = eval_mod.score_accuracy("A3", "T2", "DEV-1", truth)
    assert half.category_correct and not half.tier_correct
    assert half.score == 0.5

    assert eval_mod.score_accuracy("A3", "T1", "DEV-1", {}) is None


def test_score_confidence_rewards_margin_and_penalises_fallback():
    decisive = eval_mod.score_confidence(0.9, 0.5, fallback_used=False)
    close = eval_mod.score_confidence(0.9, 0.88, fallback_used=False)
    assert decisive > close

    penalised = eval_mod.score_confidence(0.9, 0.5, fallback_used=True)
    assert penalised < decisive
    assert 0.0 <= penalised <= 1.0


def test_explanation_quality_detects_cited_fields():
    good = eval_mod.score_explanation_quality(
        "This T1 machine runs Docker for the student's high urgency coursework.",
        software_needed=["Docker"],
        urgency="high",
        main_usage=["programming or coding"],
        tier="T1",
    )
    assert good.cites_applicant_field
    assert "Docker" in good.anchors_present
    assert good.score > 0.5

    generic = eval_mod.score_explanation_quality(
        "This device is a good match for the applicant.",
        software_needed=["Docker"],
        urgency="high",
        main_usage=["programming or coding"],
        tier="T1",
    )
    assert not generic.cites_applicant_field
    assert generic.score < good.score


# ----- full run ----------------------------------------------------------


def test_run_eval_shape_and_summary():
    result = eval_mod.run_eval("sample-v1")
    assert result.model == "ai"
    assert result.dataset == "sample-v1"
    assert result.summary.n == len(result.rows) == 9

    for row in result.rows:
        assert row.scenario
        assert 0.0 <= row.confidence <= 1.0
        # Offline run → no Gemini tokens, deterministic fallback explanation.
        assert row.tokens.total == 0
        assert row.fallback_used is True
        if row.error is None:
            assert row.chosen_device_id
            assert row.explanation_quality is not None

    s = result.summary
    assert 0.0 <= s.category_accuracy <= 1.0
    assert 0.0 <= s.tier_accuracy <= 1.0
    assert s.fallback_rate == 1.0


def test_run_eval_category_accuracy_is_high():
    """Splitter assigns categories deterministically, so category accuracy
    against the labelled scenarios should be essentially perfect."""
    result = eval_mod.run_eval("sample-v1")
    assert result.summary.category_accuracy >= 0.8


def test_limit_truncates_dataset():
    result = eval_mod.run_eval("sample-v1", limit=3)
    assert len(result.rows) == 3


def test_failed_allocation_scored_as_zero_not_dropped():
    """Regression for the unequal-denominator bug: a labelled applicant with no
    allocation scores 0 and stays in the accuracy denominator, so a failing
    engine is not rewarded by a shrinking denominator."""
    truth = {"category": "A3", "tier": "T1"}
    acc = eval_mod._failed_accuracy(truth)
    assert acc is not None and acc.score == 0.0
    assert not acc.category_correct and not acc.tier_correct
    assert eval_mod._failed_accuracy({}) is None  # unlabelled applicants stay unscored

    # In a run, every labelled row is counted (n_scored == labelled rows),
    # whether or not the engine produced an allocation.
    result = eval_mod.run_eval("sample-v1")
    labelled = [r for r in result.rows if r.accuracy is not None]
    assert result.summary.n_scored == len(labelled)
    assert result.summary.mean_accuracy_score == round(
        sum(r.accuracy.score for r in labelled) / len(labelled), 3
    )
