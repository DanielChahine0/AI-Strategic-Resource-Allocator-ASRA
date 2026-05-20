"""Minimal FastAPI shim for ASRA.

Two endpoints:
  POST /match         — body: {"applicant": {...}, "inventory": [...]}
                        returns FinalMatchResult
  POST /intake/parse  — body: {"q1": "...", "q2": "...", ...}
                        returns parsed Applicant (id auto-assigned)

No DB, no auth — this is the surface a future web frontend would call.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI
from pydantic import BaseModel

from asra_matcher import engine, llm
from asra_matcher.models import Applicant, Device, FinalMatchResult

app = FastAPI(title="ASRA Matching Engine", version="0.1.0")


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
