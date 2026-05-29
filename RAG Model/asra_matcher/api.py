"""FastAPI app exposing match / parse / reingest / evaluate endpoints."""
from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()

from . import engine as engine_mod
from . import eval as eval_mod
from . import llm as llm_mod
from .models import Applicant, Device, FinalMatchResult, IntakeAnswers
from .rag import ingest as ingest_mod

app = FastAPI(title="ASRA Matcher", version="0.1.0")

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


def require_admin_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Strict, fail-closed gate for the destructive reingest endpoint.

    Unlike `require_api_key`, this denies by default: if no ASRA_API_KEY is
    configured the endpoint is disabled entirely, so a fresh deployment cannot
    have its whole vector store wiped by an unauthenticated caller.
    """
    key = os.getenv("ASRA_API_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="admin endpoint disabled: set ASRA_API_KEY to enable reingest over HTTP",
        )
    if x_api_key != key:
        raise HTTPException(status_code=401, detail="missing or invalid API key")


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


@app.post("/match", response_model=FinalMatchResult, dependencies=[Depends(require_api_key)])
def match(req: MatchRequest) -> FinalMatchResult:
    return engine_mod.match(req.applicant, req.inventory)


@app.post("/intake/parse", response_model=IntakeParseResponse, dependencies=[Depends(require_api_key)])
def parse_intake(req: IntakeParseRequest) -> IntakeParseResponse:
    res = llm_mod.parse_intake(req.raw_answers, applicant_id=req.applicant_id)
    return IntakeParseResponse(
        parsed=res.parsed,
        citations=res.citations,
        uncertain_fields=res.uncertain_fields,
        fallback_used=res.fallback_used,
    )


@app.post("/admin/reingest", dependencies=[Depends(require_admin_key)])
def reingest(rebuild: bool = False) -> dict[str, int]:
    try:
        return ingest_mod.ingest(rebuild=rebuild)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class EvaluateRequest(BaseModel):
    dataset: str = "sample-v1"
    limit: int | None = None


@app.post("/evaluate", response_model=eval_mod.EvalResult, dependencies=[Depends(require_api_key)])
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
