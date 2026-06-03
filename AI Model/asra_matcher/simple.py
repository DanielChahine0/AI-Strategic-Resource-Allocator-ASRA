"""Simplified first-come-first-serve allocator (Q1–Q4 model).

This is the token-lean replacement for the priority/category engine. It matches
on exactly four intake answers:

  Q1 os_choice  — Ubuntu / Windows / Both   → DETERMINISTIC capability filter
  Q2 main_needs — free text                 → AI fit signal
  Q3 software   — free text                 → DETERMINISTIC capability check
                                              (AI only via the combined call)
  Q4 challenge  — free text                 → AI fit signal

There is no priority, urgency, timing, category split, or tier recommendation —
allocation order is first-come-first-serve (the caller feeds applicants in
submission order). The only LLM spend is ONE combined `fit_and_explain` call
over a tiny, pre-filtered candidate set; everything else is pure Python.

Pipeline:
    inventory (refurbished, from the sheet)
      → Q1 OS-capability filter        [0 tokens]
      → Q3 software-capability check    [0 tokens]
      → deterministic pre-rank, take top-N
      → ONE AI call: needs_fit + challenge_fit + explanation   [tokens here only]
      → final weighted composite, return top 2
"""
from __future__ import annotations

import os
import re
from datetime import datetime

from pydantic import BaseModel, Field

from asra_matcher import llm, sheets
from asra_matcher.models import Device
from asra_matcher.obslog import get_logger
from asra_matcher.rules import required_software_tier
from asra_matcher.taxonomy import DeviceTier, OSChoice

_log = get_logger("ai")

# --- Tunable knobs --------------------------------------------------------
# Final composite weights over the three question signals (Q2/Q3/Q4). Q1 is a
# hard filter, not a weight. These are the only weights in the simplified model.
W_NEEDS = float(os.environ.get("ASRA_W_NEEDS", "0.40"))      # Q2
W_SOFTWARE = float(os.environ.get("ASRA_W_SOFTWARE", "0.35"))  # Q3
W_CHALLENGE = float(os.environ.get("ASRA_W_CHALLENGE", "0.25"))  # Q4

# How many pre-ranked candidates to send to the model (smaller = fewer tokens).
TOP_N_CANDIDATES = int(os.environ.get("ASRA_TOP_N_CANDIDATES", "3"))

# Windows-11 capability bar (Q1). Refurbished PCs lack a TPM column, so we
# approximate with CPU generation + RAM, the two signals the sheet carries.
WIN11_MIN_RAM_GB = int(os.environ.get("ASRA_WIN11_MIN_RAM_GB", "8"))
WIN11_MIN_INTEL_GEN = int(os.environ.get("ASRA_WIN11_MIN_INTEL_GEN", "8"))
UBUNTU_MIN_RAM_GB = int(os.environ.get("ASRA_UBUNTU_MIN_RAM_GB", "4"))

_TIER_RANK = {DeviceTier.T1: 3, DeviceTier.T2: 2, DeviceTier.T3: 1, DeviceTier.OTHER: 0}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SimpleIntake(BaseModel):
    os_choice: OSChoice = OSChoice.BOTH            # Q1
    main_needs: str = ""                           # Q2
    software: str = ""                             # Q3
    challenge: str = ""                            # Q4


class SimpleApplicant(BaseModel):
    applicant_id: str
    intake: SimpleIntake
    submitted_at: datetime | None = None           # FCFS ordering only
    area: str | None = None                        # e.g. "Etobicoke" — batch grouping only


class SimpleScore(BaseModel):
    os_capable: bool
    software_ok: bool
    software_fit: float = Field(ge=0.0, le=1.0)
    needs_fit: float = Field(ge=0.0, le=1.0)
    challenge_fit: float = Field(ge=0.0, le=1.0)
    efficiency: float = Field(ge=0.0, le=1.0)
    condition: float = Field(ge=0.0, le=1.0)
    composite: float = Field(ge=0.0, le=1.0)
    used_ai: bool = False
    notes: list[str] = Field(default_factory=list)


class SimpleMatch(BaseModel):
    device: Device
    score: SimpleScore
    explanation: str | None = None


class TokenStep(BaseModel):
    """Token spend at one pipeline step, with a running cumulative total.

    Deterministic steps (Q1 OS filter, Q3 software check, pre-rank) report 0
    tokens with kind="algorithm"; the single AI call reports its exact cost and
    kind "ai" | "cache" | "fallback".
    """

    step: str
    kind: str  # "algorithm" | "ai" | "cache" | "fallback"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cumulative_total: int = 0
    detail: str = ""


class SimpleResult(BaseModel):
    applicant_id: str
    os_choice: str
    inventory_total: int          # refurbished computers before any filter
    after_os_filter: int          # survived the Q1 capability filter
    candidates_scored: int        # sent to the AI (top-N)
    used_ai: bool                 # whether the LLM actually answered
    top: list[SimpleMatch]
    token_steps: list[TokenStep] = Field(default_factory=list)
    tokens_total: int = 0
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Q1 — OS-capability filter (deterministic, 0 tokens)
# ---------------------------------------------------------------------------


_INTEL_GEN_RE = re.compile(r"(\d{1,2})\s*(?:th|st|nd|rd)?\s*gen", re.IGNORECASE)


def _intel_generation(cpu: str) -> int | None:
    m = _INTEL_GEN_RE.search(cpu or "")
    return int(m.group(1)) if m else None


def windows11_capable(specs: dict) -> bool:
    """Approximate Windows-11 readiness from CPU generation + RAM.

    Conservative on RAM (must clear the bar when known) but lenient on unknowns
    so a sparsely-filled sheet row isn't silently excluded. AMD Ryzen and Apple
    silicon pass; Intel must be recent enough.
    """
    ram = specs.get("ram_gb")
    if isinstance(ram, int) and ram < WIN11_MIN_RAM_GB:
        return False
    cpu = str(specs.get("cpu", "")).lower()
    if "ryzen" in cpu or "apple" in cpu or "m1" in cpu or "m2" in cpu or "m3" in cpu:
        return True
    gen = _intel_generation(cpu)
    if gen is not None:
        return gen >= WIN11_MIN_INTEL_GEN
    return True  # unknown CPU + adequate/unknown RAM → don't exclude


def os_capable(device: Device, os_choice: OSChoice) -> bool:
    """Whether `device` can run the requested OS. Ubuntu is the low bar; Windows
    (and therefore "both") must clear the Windows-11 capability check."""
    ram = device.specs.get("ram_gb")
    if os_choice == OSChoice.UBUNTU:
        return not (isinstance(ram, int) and ram < UBUNTU_MIN_RAM_GB)
    return windows11_capable(device.specs)  # WINDOWS or BOTH


# ---------------------------------------------------------------------------
# Q3 — software-capability check (deterministic, 0 tokens)
# ---------------------------------------------------------------------------


def parse_software(software: str) -> list[str]:
    """Split the free-text Q3 answer into individual package names."""
    if not software:
        return []
    parts = re.split(r"[,;/]|\band\b|\n", software)
    return [p.strip() for p in parts if p.strip() and p.strip().lower() != "none"]


def software_assessment(device: Device, software_items: list[str]) -> tuple[bool, float, list[str]]:
    """Return (ok, fit, notes) for whether the device can run the requested software.

    Uses the shared capability matrix (rules.required_software_tier). Unknown
    packages add no constraint (treated as light-weight). `fit` is 1.0 when the
    device tier clears the required tier, scaled down by how far it falls short.
    """
    if device.tier is None:
        return True, 1.0, []
    required = required_software_tier(software_items)
    dev_rank = _TIER_RANK.get(device.tier, 0)
    req_rank = _TIER_RANK.get(required, 1)
    ok = dev_rank >= req_rank
    notes: list[str] = []
    if not ok:
        notes.append(
            f"tier {device.tier.value} below software requirement {required.value}"
        )
    # Graceful slope: each tier short knocks off 0.4.
    fit = max(0.0, 1.0 - 0.4 * max(0, req_rank - dev_rank))
    return ok, round(fit, 3), notes


# ---------------------------------------------------------------------------
# Deterministic pre-rank
# ---------------------------------------------------------------------------


def _efficiency(device: Device, required: DeviceTier) -> float:
    """Penalise handing out far more power than the software needs."""
    if device.tier is None:
        return 1.0
    over = max(0, _TIER_RANK.get(device.tier, 0) - _TIER_RANK.get(required, 1))
    return max(0.0, 1.0 - over / 2.0)


def _prerank_key(device: Device, software_items: list[str]) -> float:
    ok, fit, _ = software_assessment(device, software_items)
    required = required_software_tier(software_items)
    cond = device.condition / 5.0
    eff = _efficiency(device, required)
    # Deterministic score used only to choose which few devices the AI sees.
    return 0.5 * fit + 0.3 * cond + 0.2 * eff


# ---------------------------------------------------------------------------
# Per-step token measurement
# ---------------------------------------------------------------------------


_LEDGER_KEYS = ("input", "output", "total", "calls", "cache_hits", "fallbacks")


def _measure_ai(thunk):
    """Run `thunk` and return (result, delta) where delta is the token usage
    attributable to it.

    Works whether or not an outer token ledger is active (e.g. the batch
    runner): if one is active we diff a snapshot so we never disturb it; if not,
    we start a local ledger just for this call.
    """
    outer = llm.read_token_capture()
    if outer is None:
        led = llm.start_token_capture()
        try:
            result = thunk()
        finally:
            delta = {k: int(led.get(k, 0)) for k in _LEDGER_KEYS}
            llm.stop_token_capture()
        return result, delta
    before = {k: int(outer.get(k, 0)) for k in _LEDGER_KEYS}
    result = thunk()
    after = llm.read_token_capture() or {}
    delta = {k: int(after.get(k, 0)) - before[k] for k in _LEDGER_KEYS}
    return result, delta


def _ai_kind(delta: dict) -> str:
    if delta.get("calls", 0) > 0:
        return "ai"
    if delta.get("cache_hits", 0) > 0:
        return "cache"
    return "fallback"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def allocate(
    applicant: SimpleApplicant,
    inventory: list[Device] | None = None,
    *,
    top_n: int | None = None,
) -> SimpleResult:
    """Run the simplified pipeline for one applicant and return the top 2 matches.

    `inventory` defaults to the live refurbished catalogue from the Google Sheet
    (`sheets.load_inventory`). Pass an explicit list to score against a fixed set
    (tests, batch runs).

    Every step's token cost is recorded in `token_steps` (deterministic steps =
    0 tokens; the lone AI call carries the spend) with a running cumulative total.
    """
    top_n = top_n or TOP_N_CANDIDATES
    intake = applicant.intake
    notes: list[str] = []

    steps: list[TokenStep] = []
    cum = 0

    def add_step(step: str, kind: str, *, inp: int = 0, out: int = 0, tot: int = 0, detail: str = "") -> None:
        nonlocal cum
        cum += tot
        steps.append(
            TokenStep(
                step=step, kind=kind, input_tokens=inp, output_tokens=out,
                total_tokens=tot, cumulative_total=cum, detail=detail,
            )
        )
        _log.info("· step %-14s %-9s tokens=%-4d cum=%-4d %s", step, kind, tot, cum, detail)

    if inventory is None:
        inventory, _counts = sheets.load_inventory()
    inventory_total = len(inventory)

    # Q1 — OS capability filter (deterministic, 0 tokens).
    os_ok = [d for d in inventory if os_capable(d, intake.os_choice)]
    add_step(
        "os_filter", "algorithm",
        detail=f"{inventory_total}→{len(os_ok)} can run {intake.os_choice.value}",
    )
    if not os_ok:
        notes.append(f"No refurbished computer can run '{intake.os_choice.value}'.")
        return SimpleResult(
            applicant_id=applicant.applicant_id,
            os_choice=intake.os_choice.value,
            inventory_total=inventory_total,
            after_os_filter=0,
            candidates_scored=0,
            used_ai=False,
            top=[],
            token_steps=steps,
            tokens_total=cum,
            notes=notes,
        )

    # Q3 — software capability (deterministic, 0 tokens). Prefer devices that can
    # run the software; if none can, relax to all OS-capable devices and note it.
    software_items = parse_software(intake.software)
    required = required_software_tier(software_items)
    runnable = [d for d in os_ok if software_assessment(d, software_items)[0]]
    if not runnable:
        runnable = os_ok
        if software_items:
            notes.append(
                "No device fully meets the software requirement; ranking on the "
                "closest available machines."
            )
    add_step(
        "software_check", "algorithm",
        detail=f"{len(os_ok)}→{len(runnable)} runnable; software needs tier {required.value}",
    )

    # Deterministic pre-rank → take the top-N the AI will actually see.
    runnable.sort(key=lambda d: _prerank_key(d, software_items), reverse=True)
    candidates = runnable[:top_n]
    add_step("prerank", "algorithm", detail=f"top {len(candidates)} of {len(runnable)} sent to AI")

    # ONE combined AI call: needs_fit + challenge_fit + explanation per candidate.
    (assessments, used_ai), delta = _measure_ai(
        lambda: llm.fit_and_explain(
            intake.main_needs, intake.software, intake.challenge, candidates
        )
    )
    add_step(
        "fit_explain", _ai_kind(delta),
        inp=delta["input"], out=delta["output"], tot=delta["total"],
        detail=f"{len(candidates)} device(s) in 1 combined call",
    )

    matches: list[SimpleMatch] = []
    for d in candidates:
        ok, sw_fit, sw_notes = software_assessment(d, software_items)
        a = assessments.get(d.id, {})
        needs_fit = float(a.get("needs_fit", 0.6))
        challenge_fit = float(a.get("challenge_fit", 0.6))
        composite = round(
            W_NEEDS * needs_fit + W_SOFTWARE * sw_fit + W_CHALLENGE * challenge_fit, 3
        )
        matches.append(
            SimpleMatch(
                device=d,
                score=SimpleScore(
                    os_capable=True,
                    software_ok=ok,
                    software_fit=sw_fit,
                    needs_fit=round(needs_fit, 3),
                    challenge_fit=round(challenge_fit, 3),
                    efficiency=round(_efficiency(d, required), 3),
                    condition=round(d.condition / 5.0, 3),
                    composite=composite,
                    used_ai=used_ai,
                    notes=sw_notes,
                ),
                explanation=a.get("explanation"),
            )
        )

    matches.sort(key=lambda m: m.score.composite, reverse=True)
    if not used_ai:
        notes.append("Scored without the language model (unavailable or fell back).")

    return SimpleResult(
        applicant_id=applicant.applicant_id,
        os_choice=intake.os_choice.value,
        inventory_total=inventory_total,
        after_os_filter=len(os_ok),
        candidates_scored=len(candidates),
        used_ai=used_ai,
        top=matches[:2],
        token_steps=steps,
        tokens_total=cum,
        notes=notes,
    )
