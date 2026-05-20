"""Pydantic models for applicants, devices, and match results."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

from asra_matcher.taxonomy import (
    A3Subtrack,
    Category,
    DeviceTier,
    ItemType,
    PriorDeviceStatus,
    TechAccess,
    Urgency,
)


# ---------------------------------------------------------------------------
# Intake / Applicant
# ---------------------------------------------------------------------------


class IntakeAnswers(BaseModel):
    """Parsed answers to the 8-question intake flow.

    Free-text Q1, Q3, Q5, Q6, Q8 are normalised by `llm.parse_intake` into
    the structured fields below.
    """

    # Core 7 (from LGT framework)
    who_needs_it: str = Field(..., description="Q1 — who the device is for")
    main_usage: list[str] = Field(default_factory=list, description="Q4 — daily activities")
    software_needed: list[str] = Field(default_factory=list, description="Q5 — required software")
    shared_user_count: int = Field(1, ge=1, description="Q6 — how many users on this device")
    urgency: Urgency = Field(Urgency.MEDIUM, description="Q7 — how soon device is needed")
    purpose: list[Category] = Field(default_factory=list, description="Q2 — purpose categories")
    current_tech_access: TechAccess = Field(TechAccess.NONE, description="Q6 — current tech situation")

    # Education sub-track (drives A1/A2/A3 split)
    a3_subtrack: A3Subtrack | None = Field(None, description="Q3 — post-secondary track")
    program_name: str | None = Field(None, description="Q3 — program name (free text)")

    # Q8 — optional contextual data (all nullable)
    age_range: str | None = None
    year_arrived_canada: int | None = None
    employment_status: str | None = None
    accessibility_needs: list[str] = Field(default_factory=list)
    language_preference: str | None = None
    applied_before: bool = False
    prior_device_status: PriorDeviceStatus = PriorDeviceStatus.NA

    # System-managed
    waitlist_days: int = Field(0, ge=0, description="Days on the waitlist (set by system)")


class Applicant(BaseModel):
    """A full applicant record. May span multiple categories before splitting."""

    applicant_id: str
    intake: IntakeAnswers
    submitted_at: date | None = None
    notes: str | None = None


class Application(BaseModel):
    """A single-category application derived from an Applicant by the splitter.

    The engine scores each Application independently. When an applicant covers
    multiple categories, only the application with the strongest top match
    survives — the rest are reported but discarded.
    """

    applicant_id: str
    category: Category
    intake: IntakeAnswers


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


class Device(BaseModel):
    """A donated device available for allocation."""

    id: str
    item_type: ItemType
    tier: DeviceTier | None = Field(
        None,
        description="Required for computers; None for peripherals / mobile / connectivity.",
    )
    specs: dict[str, Any] = Field(default_factory=dict)
    condition: int = Field(..., ge=1, le=5, description="1 = poor, 5 = like new")
    available_from: date
    location: str | None = None
    notes: str | None = None

    @field_validator("tier")
    @classmethod
    def _computer_must_have_tier(cls, v, info):
        item_type = info.data.get("item_type")
        if item_type == ItemType.COMPUTER and v is None:
            raise ValueError("Computers must specify a tier")
        return v


# ---------------------------------------------------------------------------
# Scoring / Match results
# ---------------------------------------------------------------------------


class ScoreBreakdown(BaseModel):
    """Per-dimension scores for a single (application, device) pair.

    `fit` is the hard gate — if False the device is excluded outright and
    no composite is computed. The other four are floats in [0, 1].
    """

    fit: bool
    efficiency: float = Field(..., ge=0.0, le=1.0)
    timing: float = Field(..., ge=0.0, le=1.0)
    priority: float = Field(..., ge=0.0, le=1.0)
    condition: float = Field(..., ge=0.0, le=1.0)
    composite: float = Field(..., ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class MatchResult(BaseModel):
    """A single device match candidate."""

    device: Device
    scores: ScoreBreakdown
    explanation: str | None = None


class ApplicationResult(BaseModel):
    """Top-2 matches for a single Application."""

    application: Application
    top2: list[MatchResult]
    best_composite: float = Field(0.0, description="Composite of the #1 match; 0 if no candidates")


class FinalMatchResult(BaseModel):
    """The full output of `engine.match()`.

    `selected_application` is the winning split; `discarded_applications`
    holds the rest (still scored, but not chosen).
    """

    applicant_id: str
    selected_application: ApplicationResult
    discarded_applications: list[ApplicationResult] = Field(default_factory=list)
