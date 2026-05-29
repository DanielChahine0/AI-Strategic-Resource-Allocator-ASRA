"""Tests for the RAG evaluation-run mode.

These run fully offline: the `_offline` fixture stubs retrieval (no Chroma) and
generation (no Gemini), so the engine takes its deterministic fallback paths.
Token counts are therefore 0 and `fallback_used` is True, while accuracy /
confidence / explanation-quality are computed from the real pipeline output.
"""

from __future__ import annotations

import pytest

from asra_matcher import eval as eval_mod
from asra_matcher import llm
from asra_matcher.rag import retrieve as retrieve_mod


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Force deterministic fallbacks: no retrieval, no generation, no network."""
    monkeypatch.setattr(retrieve_mod, "query", lambda *a, **k: [])

    def _no_generate(*a, **k):
        raise RuntimeError("LLM disabled in tests")

    monkeypatch.setattr(llm, "_generate", _no_generate)


# ----- scorers -----------------------------------------------------------


def test_score_accuracy_category_and_tier():
    truth = {"category": "A3", "tier": "T1", "acceptable_tiers": ["T1"]}
    acc = eval_mod.score_accuracy("A3", "T1", "DEV-1", truth)
    assert acc.category_correct and acc.tier_correct and acc.score == 1.0

    half = eval_mod.score_accuracy("A3", "T2", "DEV-1", truth)
    assert half.category_correct and not half.tier_correct and half.score == 0.5

    assert eval_mod.score_accuracy("A3", "T1", "DEV-1", {}) is None


def test_score_confidence_rewards_margin_and_penalises_fallback():
    decisive = eval_mod.score_confidence(0.9, 0.5, fallback_used=False)
    close = eval_mod.score_confidence(0.9, 0.88, fallback_used=False)
    penalised = eval_mod.score_confidence(0.9, 0.5, fallback_used=True)
    assert decisive > close
    assert penalised < decisive
    assert 0.0 <= penalised <= 1.0


def test_explanation_quality_detects_cited_fields():
    good = eval_mod.score_explanation_quality(
        "This T1 machine runs Docker Desktop for the student's high urgency coursework.",
        software_needed=["Docker Desktop"],
        urgency="high",
        main_usage=["running Docker containers"],
        tier="T1",
    )
    generic = eval_mod.score_explanation_quality(
        "This device is a good match for the applicant.",
        software_needed=["Docker Desktop"],
        urgency="high",
        main_usage=["running Docker containers"],
        tier="T1",
    )
    assert good.cites_applicant_field and not generic.cites_applicant_field
    assert good.score > generic.score


# ----- full run ----------------------------------------------------------


def test_run_eval_shape_and_summary():
    result = eval_mod.run_eval("sample-v1")
    assert result.model == "rag"
    assert result.summary.n == len(result.rows) == 9

    for row in result.rows:
        assert row.scenario
        assert 0.0 <= row.confidence <= 1.0
        assert row.tokens.total == 0  # offline → no Gemini tokens
        assert row.fallback_used is True
        if row.error is None:
            assert row.chosen_device_id
            assert row.explanation_quality is not None

    s = result.summary
    assert 0.0 <= s.category_accuracy <= 1.0
    assert s.fallback_rate == 1.0


def test_run_eval_category_accuracy_is_high():
    result = eval_mod.run_eval("sample-v1")
    assert result.summary.category_accuracy >= 0.8


def test_limit_truncates_dataset():
    result = eval_mod.run_eval("sample-v1", limit=3)
    assert len(result.rows) == 3


def test_failed_allocation_scored_as_zero_not_dropped():
    """Regression for the unequal-denominator bug: a labelled applicant the
    engine cannot serve must score 0 and stay in the accuracy denominator,
    otherwise an engine that fails to allocate is rewarded with a smaller
    denominator than its peer."""
    result = eval_mod.run_eval("sample-v1")
    failed = [r for r in result.rows if r.error is not None]
    assert failed, "expected at least one fit-gate failure in the RAG sample run"
    for r in failed:
        assert r.accuracy is not None, "a labelled failure must carry an accuracy result"
        assert r.accuracy.score == 0.0
        assert not r.accuracy.category_correct and not r.accuracy.tier_correct

    # Every labelled row is scored; the denominator equals the labelled count.
    labelled = [r for r in result.rows if r.accuracy is not None]
    assert result.summary.n_scored == len(labelled)
    assert result.summary.error_count == len(failed)
    # Accuracy is averaged over all labelled rows, failures included.
    assert result.summary.mean_accuracy_score == round(
        sum(r.accuracy.score for r in labelled) / len(labelled), 3
    )
