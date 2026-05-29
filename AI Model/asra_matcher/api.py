"""Minimal FastAPI shim for ASRA.

Endpoints:
  POST /match          — body: {"applicant": {...}, "inventory": [...]}
                         returns FinalMatchResult
  POST /intake/parse   — body: {"q1": "...", "q2": "...", ...}
                         returns parsed Applicant (id auto-assigned)
  GET  /health
  POST /evaluate       — run the engine over a labelled dataset; returns
                         per-match rows + an aggregate summary (eval mode)
  GET  /eval/datasets  — list available eval datasets

No DB. Auth is optional: set ASRA_API_KEY to require a matching `X-API-Key`
header on the mutating / LLM-spending routes (/match, /intake/parse, /evaluate).
This is the surface a future web frontend would call.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from asra_matcher import engine, llm
from asra_matcher import eval as eval_mod
from asra_matcher.models import Applicant, Device, FinalMatchResult

app = FastAPI(title="ASRA Matching Engine", version="0.1.0")

# CORS: default to the local Vite dev-server origins; override with a
# comma-separated ASRA_CORS_ORIGINS for other deployments. A wildcard "*" let
# any website the user visited drive this PII-handling API from their browser.
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
    """Optional API-key gate for mutating / LLM-spending routes.

    Enforced only when ASRA_API_KEY is set in the environment, so the local
    one-command demo runs with no key. When a key IS configured, requests must
    send a matching `X-API-Key` header or get a 401.
    """
    key = os.getenv("ASRA_API_KEY", "").strip()
    if not key:
        return
    if x_api_key != key:
        raise HTTPException(status_code=401, detail="missing or invalid API key")


class MatchRequest(BaseModel):
    applicant: Applicant
    inventory: list[Device]


@app.post("/match", response_model=FinalMatchResult, dependencies=[Depends(require_api_key)])
def post_match(req: MatchRequest) -> FinalMatchResult:
    return engine.match(req.applicant, req.inventory)


class IntakeParseRequest(BaseModel):
    q1: str = ""
    q2: str = ""
    q3: str = ""
    q4: str = ""
    q5: str = ""
    q6: str = ""
    q7: str = ""
    q8: str = ""
    applicant_id: str | None = None


@app.post("/intake/parse", response_model=Applicant, dependencies=[Depends(require_api_key)])
def post_intake_parse(req: IntakeParseRequest) -> Applicant:
    raw = req.model_dump(exclude={"applicant_id"})
    intake_answers = llm.parse_intake(raw)
    applicant_id = req.applicant_id or f"app-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    return Applicant(
        applicant_id=applicant_id,
        intake=intake_answers,
        submitted_at=datetime.now().date(),
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "llm_available": str(llm.is_available())}


@app.get("/status")
def status(probe: bool = False) -> dict:
    """Live model state for the dashboard: which generation model is wired up,
    whether it is serving live Gemini output or running on deterministic
    fallbacks, quota/retry details from the last 429, and this session's
    call stats. Pass ?probe=true to spend one cheap call confirming the
    model answers right now (costs quota); default is a zero-cost snapshot
    derived from real calls made this session.
    """
    return llm.model_status(probe=probe)


class EvaluateRequest(BaseModel):
    dataset: str = "sample-v1"
    limit: int | None = None


@app.post("/evaluate", response_model=eval_mod.EvalResult, dependencies=[Depends(require_api_key)])
def post_evaluate(req: EvaluateRequest) -> eval_mod.EvalResult:
    return eval_mod.run_eval(dataset=req.dataset, limit=req.limit)


@app.get("/eval/datasets")
def eval_datasets() -> dict[str, list[str]]:
    return {"datasets": eval_mod.available_datasets()}


class DatasetResponse(BaseModel):
    dataset: str
    applicants: list[Applicant]
    inventory: list[Device]
    ground_truth: dict[str, Any]


@app.get("/eval/dataset/{dataset}", response_model=DatasetResponse)
def eval_dataset(dataset: str) -> DatasetResponse:
    """Raw labelled dataset (applicants + inventory + ground-truth labels) for
    the frontend's read-only dataset viewer. Read-only; runs no matching."""
    try:
        applicants, inventory, ground_truth = eval_mod.load_dataset(dataset)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return DatasetResponse(
        dataset=dataset,
        applicants=applicants,
        inventory=inventory,
        ground_truth=ground_truth,
    )
