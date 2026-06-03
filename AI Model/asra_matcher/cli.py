"""Command-line interface for the simplified ASRA allocator.

Usage (run from this model's directory):
  python -m asra_matcher allocate path/to/applicant.json
      applicant.json: {"applicant_id": "...", "intake": {"os_choice": "windows",
      "main_needs": "...", "software": "...", "challenge": "..."}}
      Inventory defaults to the live refurbished Google Sheet.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from asra_matcher import simple


def _cmd_allocate(args: argparse.Namespace) -> int:
    applicant = simple.SimpleApplicant.model_validate_json(Path(args.applicant).read_text())
    result = simple.allocate(applicant, top_n=args.top_n)
    print(result.model_dump_json(indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="asra_matcher", description="ASRA simplified allocator")
    sub = parser.add_subparsers(dest="command", required=True)

    p_alloc = sub.add_parser("allocate", help="allocate one applicant (Q1–Q4) against live inventory")
    p_alloc.add_argument("applicant", help="path to a SimpleApplicant JSON file")
    p_alloc.add_argument("--top-n", type=int, default=None, help="candidates to send to the model")
    p_alloc.set_defaults(func=_cmd_allocate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
