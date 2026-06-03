"""Shared pytest fixtures: fake KB on disk, deterministic embedder, in-memory Chroma."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

import pytest

from asra_matcher.models import Device
from asra_matcher.taxonomy import DeviceTier, ItemType

EMBED_DIM = 64


def _deterministic_vec(text: str, dim: int = EMBED_DIM) -> list[float]:
    """Hash text → seed → pseudo-random vector in [-1, 1]. Same input ⇒ same output."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    vec = [0.0] * dim
    for t in tokens:
        h = hashlib.sha256(t.encode("utf-8")).digest()
        for i in range(dim):
            byte = h[i % len(h)]
            vec[i] += (byte - 127.5) / 127.5
    # L2 normalize so cosine distance is meaningful.
    norm = sum(x * x for x in vec) ** 0.5
    if norm == 0:
        return [1.0 / (dim ** 0.5)] * dim
    return [x / norm for x in vec]


@pytest.fixture
def fake_embed():
    def _embed(texts: list[str]) -> list[list[float]]:
        return [_deterministic_vec(t) for t in texts]
    return _embed


@pytest.fixture
def fake_kb_path() -> Path:
    """Path to the test fake KB tree."""
    return Path(__file__).parent / "fixtures" / "fake_kb"


@pytest.fixture
def in_memory_chroma_client(tmp_path):
    import chromadb
    return chromadb.EphemeralClient()


@pytest.fixture
def sample_inventory() -> list[Device]:
    return [
        Device(id="DEV-T1A", item_type=ItemType.COMPUTER, tier=DeviceTier.T1, specs={}, condition=5, available_from=date(2026, 5, 15)),
        Device(id="DEV-T2A", item_type=ItemType.COMPUTER, tier=DeviceTier.T2, specs={}, condition=4, available_from=date(2026, 5, 14)),
        Device(id="DEV-T3A", item_type=ItemType.COMPUTER, tier=DeviceTier.T3, specs={}, condition=4, available_from=date(2026, 5, 12)),
    ]
