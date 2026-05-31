#!/usr/bin/env python3
"""Build the sample-v2 dataset from raw generated records.

This is the *authoritative* step: it imports the real AI-Model `rules.py` so the
ground-truth labels are derived from the same logic both engines run — never
hand-guessed. It also self-heals the generated applicants so the on-disk records
and the labels are always consistent:

  • drops any requested software a category's allowed tiers cannot run (so the
    fit gate can always satisfy the record and the label stays achievable),
  • backfills a missing A3 sub-track,
  • clamps out-of-range numeric fields, and
  • forces non-computer devices to tier=null / computers to a valid tier.

Inputs : sample_data_v2/_raw_generated.json   ({applicants:[...], devices:[...]})
Outputs: sample_data_v2/applicants/<id>.json  (one canonical AI-superset record)
         sample_data_v2/inventory.json
         sample_data_v2/ground_truth.json

Run with the AI-Model venv:
  "AI Model/.venv/bin/python" sample_data_v2/build_ground_truth.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
# Resolve `asra_matcher` to the AI-Model source regardless of the active venv.
sys.path.insert(0, str(ROOT / "AI Model"))

from asra_matcher import rules  # noqa: E402
from asra_matcher.models import Applicant  # noqa: E402
from asra_matcher.taxonomy import A3Subtrack, Category, DeviceTier  # noqa: E402

TIER_RANK = {DeviceTier.T1: 3, DeviceTier.T2: 2, DeviceTier.T3: 1, DeviceTier.OTHER: 0}

RAW = HERE / "_raw_generated.json"
APPLICANTS_DIR = HERE / "applicants"
INVENTORY_OUT = HERE / "inventory.json"
GROUND_TRUTH_OUT = HERE / "ground_truth.json"

# Scenario label per (category, subtrack).
_A3_SCENARIO = {
    A3Subtrack.ARTS: "A3-arts",
    A3Subtrack.SCIENCE: "A3-science",
    A3Subtrack.SOFTWARE_ENGINEERING: "A3-swe",
    A3Subtrack.BUSINESS: "A3-business",
}


def _max_allowed_tier(category: Category, intake) -> DeviceTier:
    allowed = rules.allowed_tiers(category, intake)
    return max(allowed, key=lambda t: TIER_RANK[t]) if allowed else DeviceTier.T3


def _strip_infeasible_software(category: Category, intake) -> list[str]:
    """Drop software the category's allowed tiers can't run, so the label the
    rules derive is always achievable by the engine's fit gate."""
    ceiling = _max_allowed_tier(category, intake)
    kept, dropped = [], []
    for s in intake.software_needed:
        req = rules.required_software_tier([s])
        if TIER_RANK[req] > TIER_RANK[ceiling]:
            dropped.append(s)
        else:
            kept.append(s)
    return kept, dropped


def _infer_subtrack(intake) -> A3Subtrack:
    sw = " ".join(intake.software_needed).lower()
    if rules.required_software_tier(intake.software_needed) == DeviceTier.T1 or "code" in sw or "intellij" in sw:
        return A3Subtrack.SOFTWARE_ENGINEERING
    if any(k in sw for k in ("photoshop", "illustrator", "indesign", "figma", "affinity", "audition")):
        return A3Subtrack.ARTS
    if any(k in sw for k in ("matlab", "rstudio", "spss", "stata", "jupyter")):
        return A3Subtrack.SCIENCE
    return A3Subtrack.SCIENCE


def _category_of(purpose: list[Category]) -> Category:
    if len(purpose) == 1:
        return purpose[0]
    s = set(purpose)
    # Only documented multi-category combo in this dataset: newcomer + employment.
    # Per kb/lgt_policies/multi_category_selection.md + decision_13, the
    # employment lens wins for a job-searching newcomer.
    if s == {Category.F, Category.C}:
        return Category.C
    raise ValueError(f"undocumented multi-category combo: {sorted(p.value for p in purpose)}")


def _mobile_friendly(applicant: Applicant) -> bool:
    text = " ".join(
        filter(None, [applicant.notes or "", applicant.intake.who_needs_it or ""])
    ).lower()
    return "tablet" in text


def _derive_label(applicant: Applicant) -> dict:
    intake = applicant.intake
    category = _category_of(intake.purpose)

    if category == Category.A3 and intake.a3_subtrack is None:
        intake.a3_subtrack = _infer_subtrack(intake)

    allowed = rules.allowed_tiers(category, intake)
    feasible = {t for t in allowed if rules.device_meets_software(t, intake.software_needed)}
    if not feasible:
        feasible = set(allowed) or {DeviceTier.T3}
    primary = min(feasible, key=lambda t: TIER_RANK[t])  # most-efficient sufficient tier
    acceptable = [primary.value]

    # Precedent widening: seniors / newcomers open to a tablet may also take a
    # non-tiered (OTHER) device. Mirrors v1's app-D-senior-vision label.
    if category in (Category.D, Category.F) and not intake.software_needed and _mobile_friendly(applicant):
        acceptable.append("OTHER")

    if category == Category.A3:
        scenario = _A3_SCENARIO.get(intake.a3_subtrack, "A3")
    elif set(intake.purpose) == {Category.F, Category.C}:
        scenario = "FC"
    else:
        scenario = category.value

    return {
        "scenario": scenario,
        "category": category.value,
        "tier": primary.value,
        "acceptable_tiers": acceptable,
    }


def _sanitize_device(d: dict) -> dict:
    d = dict(d)
    it = d.get("item_type")
    if it != "computer":
        d["tier"] = None
    else:
        tier = d.get("tier")
        if tier not in ("T1", "T2", "T3"):
            ram = (d.get("specs") or {}).get("ram_gb", 0) or 0
            d["tier"] = "T1" if ram >= 32 else "T2" if ram >= 16 else "T3"
    cond = d.get("condition", 3)
    d["condition"] = max(1, min(5, int(cond)))
    return d


def main() -> int:
    raw = json.loads(RAW.read_text())
    raw_applicants = raw.get("applicants", [])
    raw_devices = raw.get("devices", [])

    # Clean out any prior generated applicant files so reruns are deterministic.
    for old in APPLICANTS_DIR.glob("*.json"):
        old.unlink()

    ground_truth: dict[str, dict] = {}
    changes: list[str] = []
    seen_ids: set[str] = set()
    written = 0

    for rec in raw_applicants:
        rec = dict(rec)
        intake = dict(rec.get("intake", {}))
        # Clamp numerics.
        intake["shared_user_count"] = max(1, int(intake.get("shared_user_count", 1) or 1))
        intake["waitlist_days"] = max(0, int(intake.get("waitlist_days", 0) or 0))
        rec["intake"] = intake

        applicant = Applicant.model_validate(rec)  # raises on any schema violation

        # Self-heal: drop software the category cannot run.
        category = _category_of(applicant.intake.purpose)
        if category == Category.A3 and applicant.intake.a3_subtrack is None:
            applicant.intake.a3_subtrack = _infer_subtrack(applicant.intake)
        kept, dropped = _strip_infeasible_software(category, applicant.intake)
        if dropped:
            applicant.intake.software_needed = kept
            changes.append(f"{applicant.applicant_id}: dropped infeasible software {dropped}")

        label = _derive_label(applicant)

        aid = applicant.applicant_id
        if aid in seen_ids:
            raise SystemExit(f"duplicate applicant_id: {aid}")
        seen_ids.add(aid)
        ground_truth[aid] = label

        out = applicant.model_dump(mode="json", exclude_none=False)
        (APPLICANTS_DIR / f"{aid}.json").write_text(
            json.dumps(out, indent=2, ensure_ascii=False) + "\n"
        )
        written += 1

    devices = [_sanitize_device(d) for d in raw_devices]
    INVENTORY_OUT.write_text(json.dumps(devices, indent=2, ensure_ascii=False) + "\n")

    gt_doc = {
        "dataset": "sample-v2",
        "_note": (
            "Expected category + tier per applicant, derived programmatically from the "
            "AI-Model rules.py (allowed_tiers + required_software_tier) by "
            "build_ground_truth.py — the same logic both engines run. tier is the "
            "most-efficient sufficient tier within the rule-allowed set; acceptable_tiers "
            "widens to OTHER only for tablet-friendly seniors/newcomers, mirroring "
            "sample-v1's precedent convention."
        ),
        "applicants": ground_truth,
    }
    GROUND_TRUTH_OUT.write_text(json.dumps(gt_doc, indent=2, ensure_ascii=False) + "\n")

    # Summary.
    from collections import Counter
    by_cat = Counter(v["category"] for v in ground_truth.values())
    by_tier = Counter(v["tier"] for v in ground_truth.values())
    dev_types = Counter(d["item_type"] for d in devices)
    dev_tiers = Counter(d.get("tier") for d in devices if d["item_type"] == "computer")

    print(f"applicants written : {written}")
    print(f"  by category      : {dict(sorted(by_cat.items()))}")
    print(f"  by tier label    : {dict(sorted(by_tier.items()))}")
    print(f"devices written    : {len(devices)}")
    print(f"  by item_type     : {dict(sorted(dev_types.items()))}")
    print(f"  computer tiers   : {dict(sorted(dev_tiers.items()))}")
    if changes:
        print(f"self-heal changes  : {len(changes)}")
        for c in changes:
            print(f"    - {c}")
    else:
        print("self-heal changes  : none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
