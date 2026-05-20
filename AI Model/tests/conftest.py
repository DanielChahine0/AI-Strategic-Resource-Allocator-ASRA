"""Shared pytest fixtures.

The most important hook here disables LLM calls during the default test run
by patching `is_available()` to False. The integration test re-enables it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from asra_matcher import llm
from asra_matcher.models import Applicant, Device, IntakeAnswers
from asra_matcher.taxonomy import (
    Category,
    DeviceTier,
    ItemType,
    PriorDeviceStatus,
    TechAccess,
    Urgency,
)

FIXED_TODAY = date(2026, 5, 11)


@pytest.fixture(autouse=True)
def _disable_llm(monkeypatch):
    """Force every test to use the deterministic fallback paths."""
    monkeypatch.setattr(llm, "is_available", lambda: False)


# ----- Inventory fixtures ------------------------------------------------


@pytest.fixture
def t1_device() -> Device:
    return Device(
        id="T1-test",
        item_type=ItemType.COMPUTER,
        tier=DeviceTier.T1,
        specs={"cpu": "i9"},
        condition=5,
        available_from=date(2026, 5, 12),
    )


@pytest.fixture
def t2_device() -> Device:
    return Device(
        id="T2-test",
        item_type=ItemType.COMPUTER,
        tier=DeviceTier.T2,
        specs={"cpu": "i5"},
        condition=4,
        available_from=date(2026, 5, 13),
    )


@pytest.fixture
def t3_device() -> Device:
    return Device(
        id="T3-test",
        item_type=ItemType.COMPUTER,
        tier=DeviceTier.T3,
        specs={"cpu": "celeron"},
        condition=3,
        available_from=date(2026, 5, 14),
    )


@pytest.fixture
def mobile_device() -> Device:
    return Device(
        id="MOB-test",
        item_type=ItemType.MOBILE,
        specs={"device": "iPad"},
        condition=4,
        available_from=date(2026, 5, 12),
    )


# ----- Applicant builder -------------------------------------------------


def make_applicant(
    applicant_id: str = "test",
    purpose: list[Category] | None = None,
    urgency: Urgency = Urgency.MEDIUM,
    software: list[str] | None = None,
    shared: int = 1,
    tech_access: TechAccess = TechAccess.NONE,
    a3_subtrack=None,
    waitlist_days: int = 0,
    applied_before: bool = False,
    prior: PriorDeviceStatus = PriorDeviceStatus.NA,
    accessibility: list[str] | None = None,
) -> Applicant:
    return Applicant(
        applicant_id=applicant_id,
        intake=IntakeAnswers(
            who_needs_it=applicant_id,
            main_usage=["web browsing and email"],
            software_needed=software or [],
            shared_user_count=shared,
            urgency=urgency,
            purpose=purpose or [Category.E],
            current_tech_access=tech_access,
            a3_subtrack=a3_subtrack,
            accessibility_needs=accessibility or [],
            applied_before=applied_before,
            prior_device_status=prior,
            waitlist_days=waitlist_days,
        ),
    )


@pytest.fixture
def make_applicant_fn():
    return make_applicant


# ----- Sample data path --------------------------------------------------


@pytest.fixture
def sample_data_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "sample_data"
