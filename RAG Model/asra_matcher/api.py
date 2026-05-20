"""FastAPI app exposing match / parse / reingest / evaluate endpoints."""
from __future__ import annotations

from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from . import engine as engine_mod
from . import eval as eval_mod
from . import llm as llm_mod
from .models import Applicant, Device, FinalMatchResult, IntakeAnswers
from .rag import ingest as ingest_mod

app = FastAPI(title="ASRA Matcher", version="0.1.0")

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


class IntakeParseRequest(BaseModel):
    raw_answers: dict[str, Any] = Field(default_factory=dict)
    applicant_id: str = "api"


class IntakeParseResponse(BaseModel):
    parsed: IntakeAnswers
    citations: list[str]
    uncertain_fields: list[str]
    fallback_used: bool


@app.post("/match", response_model=FinalMatchResult)
def match(req: MatchRequest) -> FinalMatchResult:
    return engine_mod.match(req.applicant, req.inventory)


@app.post("/intake/parse", response_model=IntakeParseResponse)
def parse_intake(req: IntakeParseRequest) -> IntakeParseResponse:
    res = llm_mod.parse_intake(req.raw_answers, applicant_id=req.applicant_id)
    return IntakeParseResponse(
        parsed=res.parsed,
        citations=res.citations,
        uncertain_fields=res.uncertain_fields,
        fallback_used=res.fallback_used,
    )


@app.post("/admin/reingest")
def reingest(rebuild: bool = False) -> dict[str, int]:
    try:
        return ingest_mod.ingest(rebuild=rebuild)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class EvaluateRequest(BaseModel):
    dataset: str = "sample-v1"
    limit: int | None = None


@app.post("/evaluate", response_model=eval_mod.EvalResult)
def evaluate(req: EvaluateRequest) -> eval_mod.EvalResult:
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


@app.get("/health")
def health() -> dict[str, Any]:
    st = llm_mod.model_status()
    return {"status": "ok", "model_state": st["state"], "live": st["live"]}


@app.get("/status")
def status(probe: bool = False) -> dict:
    """Live model state for the dashboard: generation + embedding models,
    whether the engine is serving live Gemini output or deterministic
    fallbacks, quota/retry details from the last 429, and this session's
    call stats. Pass ?probe=true to spend one cheap generation + embedding
    call confirming the models answer right now (costs quota); default is a
    zero-cost snapshot derived from real calls made this session.
    """
    return llm_mod.model_status(probe=probe)
