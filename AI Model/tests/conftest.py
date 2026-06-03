"""Shared pytest fixtures.

Disables live LLM calls during the default test run by forcing
`is_available()` to False, so tests never touch the network or quota.
"""

from __future__ import annotations

import pytest

from asra_matcher import llm


@pytest.fixture(autouse=True)
def _disable_llm(monkeypatch):
    """Force every test onto the deterministic fallback paths."""
    monkeypatch.setattr(llm, "is_available", lambda: False)
