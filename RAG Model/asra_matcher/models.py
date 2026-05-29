"""Pydantic models for applicants, devices, intake answers, and match results."""
from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from .taxonomy import (
    A3SubTrack,
    Category,
    DeviceSituation,
    DeviceTier,
    ItemType,
    Urgency,
)


class CurrentTechAccess(BaseModel):
    has_internet: Optional[bool] = None
    device_situation: Optional[DeviceSituation] = None
    notes: Optional[str] = None


class IntakeAnswers(BaseModel):
    who_needs_it: str
    purpose: list[Category]
    a3_subtrack: Optional[A3SubTrack] = None
    a3_program_name: Optional[str] = None
    main_usage: str
    software_needed: list[str] = Field(default_factory=list)
    shared_user_count: int = 1
    urgency: Urgency
    current_tech_access: CurrentTechAccess = Field(default_factory=CurrentTechAccess)

    @field_validator("purpose")
    @classmethod
    def _ensure_purpose(cls, v: list[Category]) -> list[Category]:
        if not v:
            raise ValueError("at least one purpose category is required")
        return list(dict.fromkeys(v))

    @field_validator("shared_user_count")
    @classmethod
    def _check_shared(cls, v: int) -> int:
        if v < 1:
            raise ValueError("shared_user_count must be >= 1")
        return v


class Applicant(BaseModel):
    """Top-level applicant. Holds intake + identity + submission time for tiebreaks."""

    id: str
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    intake: IntakeAnswers


class Application(BaseModel):
    """An applicant split to a single category. The engine operates on Applications."""

    applicant_id: str
    submitted_at: datetime
    category: Category
    intake: IntakeAnswers


class Device(BaseModel):
    id: str
    item_type: ItemType
    tier: Optional[DeviceTier] = None  # required for computers
    specs: dict[str, Any] = Field(default_factory=dict)
    condition: int = Field(ge=1, le=5)
    available_from: date
    location: Optional[str] = None
    notes: Optional[str] = None


class ScoreBreakdown(BaseModel):
    fit: bool
    priority: float
    timing: float
    condition: float
    efficiency: float
    composite: float
    weights: dict[str, float]


class RetrievedChunk(BaseModel):
    text: str
    source_path: str
    namespace: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    similarity: float


class RagContext(BaseModel):
    """Bundle of retrieved chunks passed to an LLM task."""

    task: str
    chunks: list[RetrievedChunk]

    def render(self) -> str:
        if not self.chunks:
            return "(no retrieved context)"
        # Cap each chunk's rendered text so a single over-long chunk can't blow
        # up the (per-call, re-billed) context block. ~1200 chars ≈ 300 tokens.
        try:
            max_chars = int(os.environ.get("ASRA_MAX_CHUNK_CHARS", "1200"))
        except ValueError:
            max_chars = 1200
        parts = []
        for i, c in enumerate(self.chunks, 1):
            text = c.text if len(c.text) <= max_chars else c.text[:max_chars].rstrip() + " …[truncated]"
            parts.append(
                f"[{i}] source={c.source_path} namespace={c.namespace} similarity={c.similarity:.3f}\n{text}"
            )
        return "\n\n---\n\n".join(parts)


class MatchResult(BaseModel):
    """A single device's score for a single Application."""

    device: Device
    application_category: Category
    breakdown: ScoreBreakdown
    explanation: Optional[str] = None
    citations: list[str] = Field(default_factory=list)


class FinalMatchResult(BaseModel):
    """The engine's final answer for an applicant: best application + top 2 devices."""

    applicant_id: str
    chosen_application: Application
    top_matches: list[MatchResult]
    discarded_applications: list[Application] = Field(default_factory=list)
    retrieval_trace: dict[str, list[RetrievedChunk]] = Field(default_factory=dict)
    explanations: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    # Confidence of the RAG tier recommendation for the chosen application
    # (A3 / C only; None otherwise). Additive — surfaced for the eval harness.
    chosen_tier_confidence: Optional[float] = None
