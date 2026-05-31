#!/usr/bin/env python3
"""Validate the sample-v2 dataset loads cleanly through the RAG engine's adapter.

The RAG engine reads the same canonical (AI-superset) files but reshapes three
fields at load via `_canonical_to_rag_applicant`. This confirms every v2 record
survives that adapter and that the inventory validates against the RAG Device
model — i.e. the dataset is byte-compatible with BOTH engines.

Run with the RAG-Model venv:
  "RAG Model/.venv/bin/python" sample_data_v2/_validate_rag.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "RAG Model"))

from asra_matcher.eval import _canonical_to_rag_applicant  # noqa: E402
from asra_matcher.models import Device  # noqa: E402
from asra_matcher.splitter import split  # noqa: E402

errors = 0
apps = 0
cats: Counter = Counter()
for path in sorted((HERE / "applicants").glob("*.json")):
    try:
        applicant = _canonical_to_rag_applicant(json.loads(path.read_text()))
        for app in split(applicant):
            cats[app.category.value] += 1
        apps += 1
    except Exception as exc:  # noqa: BLE001
        errors += 1
        print(f"  APPLICANT FAIL {path.name}: {exc!r}")

devs = 0
for d in json.loads((HERE / "inventory.json").read_text()):
    try:
        Device.model_validate(d)
        devs += 1
    except Exception as exc:  # noqa: BLE001
        errors += 1
        print(f"  DEVICE FAIL {d.get('id')}: {exc!r}")

print(f"RAG adapter: {apps} applicants OK, {devs} devices OK, {errors} errors")
print(f"  split applications by category: {dict(sorted(cats.items()))}")
raise SystemExit(1 if errors else 0)
