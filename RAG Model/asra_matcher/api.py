"""FastAPI surface for the simplified ASRA allocator (RAG variant).

Endpoints:
  GET  /inventory       — live refurbished inventory from the Google Sheet
  POST /allocate        — one applicant (Q1–Q4) → top matches + per-step ledger
  POST /batch           — many applicants FCFS, spread across the API-key pool
  POST /impact          — run the mock dataset (optionally one area) → impact
  POST /admin/reingest  — rebuild the vector store (admin-gated)
  GET  /status, /health
"""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

from . import batch as batch_mod
from . import eval_simple as eval_simple_mod
from . import llm as llm_mod
from . import sheets as sheets_mod
from . import simple as simple_mod
from .models import Device
from .obslog import get_logger
from .rag import ingest as ingest_mod

app = FastAPI(title="ASRA Matcher", version="0.2.0")

# Startup banner — emitted once when uvicorn imports this module.
_boot = get_logger("rag")
_boot_status = llm_mod.model_status()
_boot.info(
    "ASRA RAG Model API booting — gen=%s · embed=%s · keys=%d · google-genai SDK=%s · state=%s",
    _boot_status["model"],
    _boot_status["embedding_model"],
    _boot_status.get("keys_total", 0),
    "ok" if _boot_status["sdk_installed"] else "MISSING (fallbacks only)",
    _boot_status["state"],
)

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
    """Optional API-key gate for LLM-spending routes (enforced only when
    ASRA_API_KEY is set)."""
    key = os.getenv("ASRA_API_KEY", "").strip()
    if not key:
        return
    if x_api_key != key:
        raise HTTPException(status_code=401, detail="missing or invalid API key")


def require_admin_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Strict, fail-closed gate for the destructive reingest endpoint."""
    key = os.getenv("ASRA_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="admin endpoint disabled: set ASRA_API_KEY to enable reingest over HTTP",
        )
    if x_api_key != key:
        raise HTTPException(status_code=401, detail="missing or invalid API key")


class InventoryResponse(BaseModel):
    devices: list[Device]
    counts: dict[str, Any]


@app.get("/inventory", response_model=InventoryResponse)
def get_inventory(refresh: bool = False) -> InventoryResponse:
    """Live refurbished inventory pulled from the LGT Google Sheet (refurbished-
    ready computers only). Pass ?refresh=true to bypass the TTL cache."""
    devices, counts = sheets_mod.load_inventory(force=refresh)
    return InventoryResponse(devices=devices, counts=counts)


class AllocateRequest(BaseModel):
    applicant: simple_mod.SimpleApplicant
    inventory: list[Device] | None = None
    top_n: int | None = None


@app.post("/allocate", response_model=simple_mod.SimpleResult, dependencies=[Depends(require_api_key)])
def allocate(req: AllocateRequest) -> simple_mod.SimpleResult:
    """Simplified Q1–Q4 first-come-first-serve allocation (grounded RAG variant).

    Q1 (OS) and the software-capability check are deterministic (0 tokens); the
    only LLM spend is one grounded fit+explain call over the top-N pre-filtered
    candidates. Inventory defaults to the live refurbished sheet.
    """
    return simple_mod.allocate(req.applicant, req.inventory, top_n=req.top_n)


class BatchRequest(BaseModel):
    applicants: list[simple_mod.SimpleApplicant]
    inventory: list[Device] | None = None
    group_by: str = "submission"   # "submission" | "area" | "none"
    batch_size: int = 10
    top_n: int | None = None


@app.post("/batch", response_model=batch_mod.BatchResult, dependencies=[Depends(require_api_key)])
def batch_run(req: BatchRequest) -> batch_mod.BatchResult:
    """Run a list of applicants first-come-first-serve through the simplified
    allocator, spreading Gemini calls across the API-key pool."""
    return batch_mod.run_batch(
        req.applicants, req.inventory,
        group_by=req.group_by, batch_size=req.batch_size, top_n=req.top_n,
    )


class ImpactRequest(BaseModel):
    area: str | None = None
    group_by: str = "area"
    batch_size: int = 10


@app.post("/impact", response_model=eval_simple_mod.ImpactReport, dependencies=[Depends(require_api_key)])
def impact(req: ImpactRequest) -> eval_simple_mod.ImpactReport:
    """Run the simplified Q1–Q4 mock applicants (optionally one area, e.g.
    Etobicoke) through the allocator against live refurbished inventory and
    return an impact summary (grounded RAG variant)."""
    return eval_simple_mod.run_impact(req.area, group_by=req.group_by, batch_size=req.batch_size)


@app.post("/admin/reingest", dependencies=[Depends(require_admin_key)])
def reingest(rebuild: bool = False) -> dict[str, int]:
    try:
        return ingest_mod.ingest(rebuild=rebuild)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/status")
def status(probe: bool = False) -> dict:
    """Live model + key-pool health for the dashboard. Pass ?probe=true to spend
    one cheap generation + embedding call confirming both answer right now."""
    return llm_mod.model_status(probe=probe)


@app.get("/health")
def health() -> dict[str, Any]:
    st = llm_mod.model_status()
    return {"status": "ok", "model_state": st["state"], "live": st["live"]}
