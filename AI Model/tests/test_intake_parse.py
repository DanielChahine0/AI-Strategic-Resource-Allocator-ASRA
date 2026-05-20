"""Heuristic intake parser (used as fallback when LLM unavailable).

The autouse `_disable_llm` fixture forces this code path.
"""

from __future__ import annotations

from asra_matcher import llm
from asra_matcher.taxonomy import A3Subtrack, Category, TechAccess, Urgency


def test_parse_multi_category_FC():
    raw = {
        "q1": "myself, newcomer to canada and looking for work",
        "q2": "2, 5",
        "q3": "",
        "q4": "1, 3",
        "q5": "Zoom, Word",
        "q6": "two people, only phone right now",
        "q7": "2",
        "q8": "I arrived in 2025, age 30",
    }
    parsed = llm.parse_intake(raw)
    assert Category.F in parsed.purpose
    assert Category.C in parsed.purpose
    assert parsed.urgency == Urgency.HIGH
    assert parsed.current_tech_access == TechAccess.PHONE_ONLY
    assert parsed.shared_user_count == 2
    assert parsed.year_arrived_canada == 2025
    assert "Zoom" in parsed.software_needed


def test_parse_cs_student():
    raw = {
        "q1": "myself",
        "q2": "1",
        "q3": "3 computer science at york",
        "q4": "6",
        "q5": "Docker, IntelliJ",
        "q6": "just me, very old laptop",
        "q7": "2",
        "q8": "skip",
    }
    parsed = llm.parse_intake(raw)
    assert Category.A3 in parsed.purpose
    assert parsed.a3_subtrack == A3Subtrack.SOFTWARE_ENGINEERING
    assert "computer science" in (parsed.program_name or "").lower()
    assert parsed.current_tech_access == TechAccess.OUTDATED_DEVICE


def test_parse_senior_vision():
    raw = {
        "q1": "myself, retired",
        "q2": "4",
        "q3": "",
        "q4": "1, 2, 5",
        "q5": "none",
        "q6": "just me, no device at all",
        "q7": "3",
        "q8": "I'm 68, my eyes aren't great",
    }
    parsed = llm.parse_intake(raw)
    assert Category.E in parsed.purpose
    assert "vision" in parsed.accessibility_needs
    assert parsed.current_tech_access == TechAccess.NONE


def test_parse_school_kid_K6():
    raw = {
        "q1": "my 9 year old son",
        "q2": "1",
        "q3": "1",
        "q4": "1, 3, 4",
        "q5": "none",
        "q6": "two people share, only phone",
        "q7": "2",
        "q8": "",
    }
    parsed = llm.parse_intake(raw)
    assert Category.A1 in parsed.purpose
