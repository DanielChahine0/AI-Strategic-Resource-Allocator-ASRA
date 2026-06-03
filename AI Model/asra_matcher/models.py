"""Pydantic models for the simplified allocator.

The only shared data model is :class:`Device` (inventory). Applicant intake and
match results live in :mod:`asra_matcher.simple` (the Q1–Q4 model). The legacy
priority/category models were removed in the Phase-5 simplification.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

from asra_matcher.taxonomy import DeviceTier, ItemType


class Device(BaseModel):
    """A donated, refurbished device available for allocation."""

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
