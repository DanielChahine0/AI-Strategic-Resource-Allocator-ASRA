"""FastAPI surface for the simplified ASRA allocator.

Endpoints:
  GET  /inventory   — live refurbished inventory from the Google Sheet
  POST /allocate    — one applicant (Q1–Q4) → top matches + per-step token ledger
  POST /batch       — many applicants FCFS, spread across the API-key pool
  POST /impact      — run the mock dataset (optionally one area) → impact summary
  GET  /status      — live model + key-pool health
  GET  /health

No DB. Auth is optional: set ASRA_API_KEY to require a matching `X-API-Key`
header on the LLM-spending routes (/allocate, /batch, /impact).
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from asra_matcher import batch, eval_simple, llm, sheets, simple
from asra_matcher.models import Device
from asra_matcher.obslog import get_logger

app = FastAPI(title="ASRA Matching Engine", version="0.2.0")

# Startup banner — emitted once when uvicorn imports this module.
_boot = get_logger("ai")
_boot_status = llm.model_status()
_boot.info(
    "ASRA AI Model API booting — model=%s · keys=%d · google-genai SDK=%s · state=%s",
    _boot_status["model"],
    _boot_status.get("keys_total", 0),
    "ok" if _boot_status["sdk_installed"] else "MISSING (fallbacks only)",
    _boot_status["state"],
)

# CORS: default to the local Vite dev-server origins; override with a
# comma-separated ASRA_CORS_ORIGINS for other deployments.
_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
_CORS_ORIGINS = [
    o.strip() for o in os.getenv("ASRA_CORS_ORIGINS", _DEFAULT_ORIGINS).split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Optional API-key gate for LLM-spending routes.

    Enforced only when ASRA_API_KEY is set in the environment, so the local
    one-command demo runs with no key. When a key IS configured, requests must
    send a matching `X-API-Key` header or get a 401.
    """
    key = os.getenv("ASRA_API_KEY", "").strip()
    if not key:
        return
    if x_api_key != key:
        raise HTTPException(status_code=401, detail="missing or invalid API key")


class InventoryResponse(BaseModel):
    devices: list[Device]
    counts: dict[str, Any]


@app.get("/inventory", response_model=InventoryResponse)
def get_inventory(refresh: bool = False) -> InventoryResponse:
    """Live refurbished inventory pulled from the LGT Google Sheet.

    Returns only devices whose Status is "Refurbished- ready for distribution"
    and whose type is an allocatable computer. `counts` reports how many rows
    were seen at each filter stage (raw_rows / refurbished / machines) plus the
    `source` (sheet / snapshot / local). Pass ?refresh=true to bypass the
    in-memory TTL cache and re-pull the sheet.
    """
    devices, counts = sheets.load_inventory(force=refresh)
    return InventoryResponse(devices=devices, counts=counts)


class AllocateRequest(BaseModel):
    applicant: simple.SimpleApplicant
    # Optional explicit inventory; when omitted, the live refurbished catalogue
    # is pulled from the Google Sheet.
    inventory: list[Device] | None = None
    top_n: int | None = None


@app.post("/allocate", response_model=simple.SimpleResult, dependencies=[Depends(require_api_key)])
def post_allocate(req: AllocateRequest) -> simple.SimpleResult:
    """Simplified Q1–Q4 first-come-first-serve allocation.

    Q1 (OS) and the software-capability check are deterministic (0 tokens); the
    only LLM spend is one combined fit+explain call over the top-N pre-filtered
    candidates. Inventory defaults to the live refurbished sheet.
    """
    return simple.allocate(req.applicant, req.inventory, top_n=req.top_n)


class BatchRequest(BaseModel):
    applicants: list[simple.SimpleApplicant]
    inventory: list[Device] | None = None
    group_by: str = "submission"   # "submission" | "area" | "none"
    batch_size: int = 10
    top_n: int | None = None


@app.post("/batch", response_model=batch.BatchResult, dependencies=[Depends(require_api_key)])
def post_batch(req: BatchRequest) -> batch.BatchResult:
    """Run a list of applicants first-come-first-serve through the simplified
    allocator, spreading Gemini calls across the API-key pool. Returns
    per-applicant matches + aggregate token totals + live key-pool state."""
    return batch.run_batch(
        req.applicants, req.inventory,
        group_by=req.group_by, batch_size=req.batch_size, top_n=req.top_n,
    )


class ImpactRequest(BaseModel):
    area: str | None = None          # e.g. "Etobicoke"; None = all areas
    group_by: str = "area"
    batch_size: int = 10


@app.post("/impact", response_model=eval_simple.ImpactReport, dependencies=[Depends(require_api_key)])
def post_impact(req: ImpactRequest) -> eval_simple.ImpactReport:
    """Run the simplified Q1–Q4 mock applicants (optionally one area, e.g.
    Etobicoke) through the allocator against live refurbished inventory and
    return an impact summary: matched count, tokens spent, and how much was
    resolved deterministically vs. with the LLM."""
    return eval_simple.run_impact(req.area, group_by=req.group_by, batch_size=req.batch_size)


@app.get("/status")
def status(probe: bool = False) -> dict:
    """Live model + key-pool health for the dashboard. Pass ?probe=true to spend
    one cheap call confirming the model answers right now (costs quota)."""
    return llm.model_status(probe=probe)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "llm_available": str(llm.is_available())}
