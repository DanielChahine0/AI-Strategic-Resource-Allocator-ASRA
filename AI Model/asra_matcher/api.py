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

No DB, no auth — this is the surface a future web frontend would call.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from asra_matcher import engine, eval as eval_mod, llm
from asra_matcher.models import Applicant, Device, FinalMatchResult

app = FastAPI(title="ASRA Matching Engine", version="0.1.0")

# Allow the local Model Comparison frontend (Vite dev server) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class MatchRequest(BaseModel):
    applicant: Applicant
    inventory: list[Device]


@app.post("/match", response_model=FinalMatchResult)
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


@app.post("/intake/parse", response_model=Applicant)
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


@app.post("/evaluate", response_model=eval_mod.EvalResult)
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
