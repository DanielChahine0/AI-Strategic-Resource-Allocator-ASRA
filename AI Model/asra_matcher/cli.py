"""Command-line interface for ASRA.

Usage:
  python -m asra_matcher intake --inventory sample_data/inventory.json
  python -m asra_matcher match path/to/applicant.json --inventory sample_data/inventory.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from asra_matcher import engine, intake
from asra_matcher.models import Applicant, Device, FinalMatchResult


def _load_inventory(path: Path) -> list[Device]:
    data = json.loads(path.read_text())
    return [Device.model_validate(item) for item in data]


def _load_applicant(path: Path) -> Applicant:
    data = json.loads(path.read_text())
    return Applicant.model_validate(data)


def _print_final(result: FinalMatchResult, writer=print) -> None:
    sel = result.selected_application
    app = sel.application
    writer("")
    writer("=" * 70)
    writer(f"Applicant: {result.applicant_id}")
    writer(f"Selected category: {app.category.value}  "
           f"(top composite: {sel.best_composite:.3f})")
    writer("=" * 70)

    if not sel.top2:
        writer("No eligible devices found.")
    for rank, m in enumerate(sel.top2, start=1):
        s = m.scores
        d = m.device
        writer("")
        writer(f"#{rank}  Device {d.id}  ({d.item_type.value}"
               f"{', tier ' + d.tier.value if d.tier else ''})")
        writer(f"     Condition: {d.condition}/5   Available from: {d.available_from}")
        if d.specs:
            writer(f"     Specs: {d.specs}")
        writer(f"     Scores -> composite {s.composite:.3f}  "
               f"priority {s.priority:.2f}  timing {s.timing:.2f}  "
               f"condition {s.condition:.2f}  efficiency {s.efficiency:.2f}")
        if m.explanation:
            writer(f"     Rationale: {m.explanation}")

    if result.discarded_applications:
        writer("")
        writer("-" * 70)
        writer("Discarded applications (this applicant covers multiple categories):")
        for dr in result.discarded_applications:
            top_id = dr.top2[0].device.id if dr.top2 else "—"
            writer(f"  - Category {dr.application.category.value}: "
                   f"best composite {dr.best_composite:.3f} (device {top_id})")


def _cmd_match(args: argparse.Namespace) -> int:
    applicant = _load_applicant(Path(args.applicant))
    inventory = _load_inventory(Path(args.inventory))
    result = engine.match(applicant, inventory)
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        _print_final(result)
    return 0


def _cmd_intake(args: argparse.Namespace) -> int:
    inventory = _load_inventory(Path(args.inventory))
    applicant = intake.run_intake(applicant_id=args.id)
    print("")
    print("Running match engine...")
    result = engine.match(applicant, inventory)
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        _print_final(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="asra", description="ASRA matching engine")
    sub = p.add_subparsers(dest="command", required=True)

    p_match = sub.add_parser("match", help="Run the match engine on a saved applicant JSON")
    p_match.add_argument("applicant", help="Path to applicant JSON")
    p_match.add_argument("--inventory", required=True, help="Path to inventory JSON")
    p_match.add_argument("--json", action="store_true", help="Output full JSON result")
    p_match.set_defaults(func=_cmd_match)

    p_intake = sub.add_parser("intake", help="Run the interactive 8-question intake")
    p_intake.add_argument("--inventory", required=True, help="Path to inventory JSON")
    p_intake.add_argument("--id", default=None, help="Applicant ID (auto if omitted)")
    p_intake.add_argument("--json", action="store_true", help="Output full JSON result")
    p_intake.set_defaults(func=_cmd_intake)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
