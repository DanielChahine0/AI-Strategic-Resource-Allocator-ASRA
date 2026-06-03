"""Tests for the round-robin Gemini key pool (pure logic, no network)."""
from __future__ import annotations

from asra_matcher import keypool


def test_discover_merges_and_dedupes(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "aaa, bbb ccc")
    monkeypatch.setenv("GEMINI_API_KEY_1", "ddd")
    monkeypatch.setenv("GEMINI_API_KEY", "aaa")  # dupe of the first
    keys = keypool.discover_keys()
    assert keys == ["aaa", "bbb", "ccc", "ddd"]


def test_round_robin_cycles_all_keys():
    pool = keypool.KeyPool(["A", "B", "C"])
    got = [pool.acquire() for _ in range(6)]
    assert got == ["A", "B", "C", "A", "B", "C"]


def test_cooling_key_is_skipped_then_recovers():
    pool = keypool.KeyPool(["A", "B", "C"])
    now = [1000.0]
    pool._now = lambda: now[0]  # type: ignore[assignment]

    pool.mark_cooling("B", 100)
    # B parked → round-robin yields only A and C.
    got = [pool.acquire() for _ in range(4)]
    assert "B" not in got
    assert set(got) == {"A", "C"}
    assert pool.live_count() == 2

    now[0] += 101  # cooldown elapsed
    assert pool.live_count() == 3
    assert "B" in [pool.acquire() for _ in range(3)]


def test_all_cooling_returns_none():
    pool = keypool.KeyPool(["A", "B"])
    now = [0.0]
    pool._now = lambda: now[0]  # type: ignore[assignment]
    pool.mark_cooling("A", 60)
    pool.mark_cooling("B", 60)
    assert pool.acquire() is None
    assert pool.all_cooling() is True
    status = pool.status()
    assert all(s["cooling"] for s in status)


def test_empty_pool():
    pool = keypool.KeyPool([])
    assert pool.acquire() is None
    assert pool.has_keys() is False
    assert pool.all_cooling() is False
