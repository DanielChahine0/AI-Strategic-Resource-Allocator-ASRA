"""Live inventory loader — pulls refurbished devices from the LGT Google Sheet.

Replaces the mock ``sample_data*/inventory.json`` with the real donation tracker.
The sheet is read via its public **CSV export** URL (no credentials), filtered to
the rows that are actually ready to hand out, and mapped onto :class:`Device`.

Two filters define "real, available inventory":
  1. ``Status`` == "Refurbished- ready for distribution"  (the only allocatable state)
  2. ``Device type`` is an actual computer — DESKTOP / LAPTOP / ALL-IN-ONE —
     so component rows (HARD DRIVE, RAM, SAS Drive) and phones/tablets drop out.

The sheet has a two-row header: row 1 is section grouping ("Computers",
"Disk Information", …) and row 2 holds the real column names. We skip row 1.

Resilience: a successful fetch is cached in-memory for ``ASRA_INVENTORY_TTL``
seconds and snapshotted to disk; if the sheet is later unreachable we serve the
last good snapshot rather than failing the request.

Configuration (env):
  ASRA_INVENTORY_SHEET_ID  — spreadsheet id (default: the LGT tracker)
  ASRA_INVENTORY_GID       — worksheet gid (default: 1340502618)
  ASRA_INVENTORY_STATUS    — required status string (default below)
  ASRA_INVENTORY_TTL       — in-memory cache seconds (default 300)
  ASRA_INVENTORY_CSV       — local CSV path to read instead of the network
                             (offline / testing; bypasses fetch + snapshot)
"""
from __future__ import annotations

import csv
import io
import os
import ssl
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

from asra_matcher.models import Device
from asra_matcher.obslog import get_logger, short
from asra_matcher.taxonomy import DeviceTier, ItemType

_log = get_logger("ai")

DEFAULT_SHEET_ID = "1Yv-2Awk6wFK0TZxRyI_1yT5QqqRKp2QMn3cU6St6tPE"
DEFAULT_GID = "1340502618"
DEFAULT_STATUS = "Refurbished- ready for distribution"

# Device-type cells that represent an allocatable computer (case-insensitive).
_COMPUTER_TYPES = {"desktop", "laptop", "all-in-one"}

# Sheet condition wording -> 1..5. Unknown/blank -> 3 (neutral "good").
_CONDITION_MAP = {
    "poor": 1,
    "fair": 2,
    "good": 3,
    "very good": 4,
    "excellent": 5,
    "like new": 5,
}

_SNAPSHOT = Path(os.environ.get("ASRA_LLM_CACHE_DIR", "./.asra_cache")) / "inventory_snapshot.csv"

# Module-level TTL cache: {"ts": monotonic, "devices": [...], "counts": {...}}.
_cache: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# URL + fetch
# ---------------------------------------------------------------------------


def csv_export_url(sheet_id: str | None = None, gid: str | None = None) -> str:
    sid = sheet_id or os.environ.get("ASRA_INVENTORY_SHEET_ID", DEFAULT_SHEET_ID)
    g = gid or os.environ.get("ASRA_INVENTORY_GID", DEFAULT_GID)
    return f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={g}"


def _ssl_context() -> ssl.SSLContext | None:
    """Best-effort verified TLS context.

    Some Python builds (notably the macOS python.org framework) ship without the
    system CA bundle, so a plain ``urlopen`` raises CERTIFICATE_VERIFY_FAILED.
    Prefer ``certifi`` (pulled in transitively by google-genai) when present.
    """
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        try:
            return ssl.create_default_context()
        except Exception:
            return None


def fetch_csv(url: str | None = None, timeout: int = 30) -> str:
    """Fetch the CSV export text. Raises on network/TLS failure."""
    url = url or csv_export_url()
    ctx = _ssl_context()
    req = urllib.request.Request(url, headers={"User-Agent": "ASRA-inventory/1.0"})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _norm(s: str) -> str:
    """Lowercase and collapse internal whitespace for tolerant comparisons."""
    return " ".join((s or "").split()).lower()


def _parse_int(value: str) -> int | None:
    digits = "".join(c for c in (value or "") if c.isdigit())
    return int(digits) if digits else None


def _parse_storage_gb(value: str) -> int | None:
    """Disk capacity cell -> GB. Treats a bare 'TB' mention as ×1000."""
    n = _parse_int(value)
    if n is None:
        return None
    if "tb" in _norm(value) and n < 100:  # e.g. "2 TB" -> 2000; "2000" stays
        n *= 1000
    return n


def _parse_date(value: str) -> date:
    raw = (value or "").strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return date.today()


def _condition_to_int(value: str) -> int:
    return _CONDITION_MAP.get(_norm(value), 3)


def _derive_tier(specs: dict[str, Any]) -> DeviceTier:
    """Deterministic tier from CPU/RAM — no LLM call.

    RAM is frequently blank in the sheet, so the CPU family is the primary
    signal: i7/i9/Ryzen 7+/Xeon -> T1, i5/Ryzen 5 -> T2, everything older/
    lower -> T3. A generous RAM figure (>=32GB) promotes to T1.
    """
    cpu = _norm(str(specs.get("cpu", "")))
    ram = specs.get("ram_gb")

    high = any(k in cpu for k in ("i7", "i9", "ryzen 7", "ryzen 9", "xeon", "m1 pro", "m2", "m3"))
    mid = any(k in cpu for k in ("i5", "ryzen 5"))

    if (isinstance(ram, int) and ram >= 32) or high:
        return DeviceTier.T1
    if mid or (isinstance(ram, int) and ram >= 8):
        return DeviceTier.T2
    return DeviceTier.T3


def _row_to_device(row: dict[str, str]) -> Device | None:
    """Map one sheet row to a Device, or None if it is not an allocatable computer."""
    dtype = _norm(row.get("Device type", ""))
    if dtype not in _COMPUTER_TYPES:
        return None

    dev_id = (row.get("LGT Donation ID") or "").strip()
    if not dev_id:
        return None

    cpu = (row.get("Processor") or "").strip()
    other_cpu = (row.get("Other Processor") or "").strip()
    if _norm(cpu).startswith("processor not listed") and other_cpu:
        cpu = other_cpu

    specs: dict[str, Any] = {"form_factor": dtype}
    if cpu:
        specs["cpu"] = cpu
    ram = _parse_int(row.get("Total RAM Included (GB)", ""))
    if ram is not None:
        specs["ram_gb"] = ram
    storage = _parse_storage_gb(row.get("Disk Capacity (GB/TB)", ""))
    if storage is not None:
        specs["storage_gb"] = storage
    disk_type = (row.get("Disk Type") or "").strip()
    if disk_type:
        specs["disk_type"] = disk_type
    brand = (row.get("Device Brand") or "").strip()
    model = (row.get("Device Model") or "").strip()
    if brand or model:
        specs["model"] = " ".join(p for p in (brand, model) if p)

    return Device(
        id=dev_id,
        item_type=ItemType.COMPUTER,
        tier=_derive_tier(specs),
        specs=specs,
        condition=_condition_to_int(row.get("Device Condition", "")),
        available_from=_parse_date(row.get("Timestamp", "")),
        location=(row.get("Hub ID") or row.get("Bin ID") or "").strip() or None,
        notes=(row.get("Refurbishment Notes") or "").strip() or None,
    )


def parse_devices(csv_text: str) -> tuple[list[Device], dict[str, int]]:
    """Parse CSV export text into refurbished computers + diagnostic counts."""
    rows = list(csv.reader(io.StringIO(csv_text)))
    if len(rows) < 2:
        return [], {"raw_rows": 0, "refurbished": 0, "machines": 0}

    header = [h.strip() for h in rows[1]]  # row 0 is section grouping; row 1 is real header
    data = rows[2:]
    want_status = _norm(os.environ.get("ASRA_INVENTORY_STATUS", DEFAULT_STATUS))

    devices: list[Device] = []
    refurbished = 0
    for raw in data:
        record = {header[i]: (raw[i] if i < len(raw) else "") for i in range(len(header))}
        if _norm(record.get("Status", "")) != want_status:
            continue
        refurbished += 1
        device = _row_to_device(record)
        if device is not None:
            devices.append(device)

    counts = {"raw_rows": len(data), "refurbished": refurbished, "machines": len(devices)}
    return devices, counts


# ---------------------------------------------------------------------------
# Public API — load with TTL cache + snapshot fallback
# ---------------------------------------------------------------------------


def _ttl() -> float:
    try:
        return float(os.environ.get("ASRA_INVENTORY_TTL", "300"))
    except ValueError:
        return 300.0


def _write_snapshot(csv_text: str) -> None:
    try:
        _SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        _SNAPSHOT.write_text(csv_text, encoding="utf-8")
    except Exception:
        pass


def load_inventory(force: bool = False) -> tuple[list[Device], dict[str, int]]:
    """Return (refurbished devices, counts), cached for ASRA_INVENTORY_TTL seconds.

    Source precedence: explicit local CSV (ASRA_INVENTORY_CSV) > live sheet >
    on-disk snapshot of the last good fetch. Network/TLS errors degrade to the
    snapshot so a transient outage never empties the catalogue.
    """
    now = time.monotonic()
    if not force and _cache and (now - _cache["ts"]) < _ttl():
        return _cache["devices"], _cache["counts"]

    local = os.environ.get("ASRA_INVENTORY_CSV", "").strip()
    if local:
        csv_text = Path(local).read_text(encoding="utf-8", errors="replace")
        source = f"local:{local}"
    else:
        try:
            csv_text = fetch_csv()
            _write_snapshot(csv_text)
            source = "sheet"
        except Exception as exc:  # network/TLS — fall back to last good snapshot
            if _SNAPSHOT.exists():
                _log.warning("inventory fetch failed (%s) — serving snapshot", short(str(exc)))
                csv_text = _SNAPSHOT.read_text(encoding="utf-8", errors="replace")
                source = "snapshot"
            else:
                _log.warning("inventory fetch failed (%s) and no snapshot available", short(str(exc)))
                raise

    devices, counts = parse_devices(csv_text)
    counts["source"] = source  # type: ignore[assignment]
    _cache.update(ts=now, devices=devices, counts=counts)
    _log.info(
        "inventory loaded from %s: %d refurbished rows -> %d allocatable computers",
        source,
        counts["refurbished"],
        counts["machines"],
    )
    return devices, counts
