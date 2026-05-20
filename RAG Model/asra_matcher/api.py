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
