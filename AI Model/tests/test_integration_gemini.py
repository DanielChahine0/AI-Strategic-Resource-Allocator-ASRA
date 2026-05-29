"""Live Gemini integration test.

Gated by `pytest -m integration`; skipped by default. Requires
GEMINI_API_KEY to be set in the environment or in .env.
"""

from __future__ import annotations

import os

import pytest

from asra_matcher import llm
from asra_matcher.taxonomy import Category, DeviceTier
from tests.conftest import make_applicant


# Disable the autouse LLM-disabling fixture for this module.
@pytest.fixture(autouse=True)
def _enable_llm():
    yield  # do nothing — the conftest fixture is still autouse, see below.


@pytest.mark.integration
def test_real_gemini_recommend_tier(monkeypatch):
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")

    # Re-enable LLM (conftest disables it).
    monkeypatch.setattr(llm, "is_available", lambda: True)

    from asra_matcher.models import Application
    app = Application(
        applicant_id="int-test",
        category=Category.A3,
        intake=make_applicant(
            purpose=[Category.A3],
            software=["Docker", "VirtualBox", "Android Studio"],
        ).intake,
    )
    result = llm.recommend_tier(app, {DeviceTier.T1, DeviceTier.T2})
    assert result["recommended_tier"] in {DeviceTier.T1, DeviceTier.T2}
    assert isinstance(result["rationale"], str) and len(result["rationale"]) > 0


@pytest.mark.integration
def test_real_gemini_parse_intake(monkeypatch):
    if not os.getenv("GEMINI_API_KEY"):
        pytest.skip("GEMINI_API_KEY not set")
    monkeypatch.setattr(llm, "is_available", lambda: True)
    raw = {
        "q1": "myself, a CS student at york",
        "q2": "1",
        "q3": "3 computer science",
        "q4": "6",
        "q5": "Docker and Android Studio",
        "q6": "just me, the laptop I have is 10 years old",
        "q7": "2",
        "q8": "I'm 20",
    }
    parsed = llm.parse_intake(raw)
    assert Category.A3 in parsed.purpose
