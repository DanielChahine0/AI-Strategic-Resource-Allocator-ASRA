"""Pydantic models for the simplified RAG allocator.

Shared models are :class:`Device` (inventory) and the retrieval types
(:class:`RetrievedChunk`, :class:`RagContext`). Applicant intake and match
results live in :mod:`asra_matcher.simple` (the Q1–Q4 model). The legacy
priority/category models were removed in the Phase-5 simplification.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from .taxonomy import DeviceTier, ItemType


class Device(BaseModel):
    id: str
    item_type: ItemType
    tier: DeviceTier | None = None  # required for computers
    specs: dict[str, Any] = Field(default_factory=dict)
    condition: int = Field(ge=1, le=5)
    available_from: date
    location: str | None = None
    notes: str | None = None


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
