"""Interactive 8-question terminal intake.

Each question is printed in plain ESL-friendly language. Raw answers are
collected verbatim (Q1, Q3 free-text, Q5, Q6, Q8 are free text; Q2/Q4
accept comma-separated option numbers; Q7 is single-select). The full set
is then sent to `llm.parse_intake` which returns a validated IntakeAnswers.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Callable

from asra_matcher import llm
from asra_matcher.models import Applicant, IntakeAnswers
from asra_matcher.taxonomy import Category

SESSION_DIR = Path("intake_sessions")


# Each question is (prompt, options-text-or-None, help-text).
# Help is shown when the user types `?`.
QUESTIONS: dict[str, tuple[str, str | None, str]] = {
    "q1": (
        "Q1. Who is this device mainly for?",
        (
            "  1. Yourself\n"
            "  2. Your child or someone you take care of\n"
            "  3. Shared use in your home\n"
            "  4. Someone else (please tell us who)"
        ),
        "Type a number 1-4. For option 4 you can also write a sentence — e.g. '4 my niece'.",
    ),
    "q2": (
        "Q2. What do you need this device for? (choose all that apply)",
        (
            "  1. School or learning             (A)\n"
            "  2. Work or job searching          (C)\n"
            "  3. Healthcare                     (B)\n"
            "  4. Staying connected / personal   (E)\n"
            "  5. Settling in Canada (newcomer)  (F)\n"
            "  6. Other (please describe)"
        ),
        "Multi-select. Type the numbers separated by commas — e.g. '1, 5'.",
    ),
    "q3": (
        "Q3. (Only if Q2 includes School or learning) What level, and what subject or program?",
        (
            "  1. K to grade 6                          (A1)\n"
            "  2. Grade 8 to high school                (A2)\n"
            "  3. College or university — please tell us the program name   (A3)"
        ),
        "If option 3, you can write the program name on the same line — e.g. '3 computer science at york'.",
    ),
    "q4": (
        "Q4. What will you do on the device most days? (choose all that apply)",
        (
            "  1. Web browsing and email\n"
            "  2. Video calls\n"
            "  3. Writing documents\n"
            "  4. Online classes\n"
            "  5. Government or healthcare websites\n"
            "  6. Programming or coding\n"
            "  7. Graphic design or video editing\n"
            "  8. Specific professional software (CAD, Adobe, statistics, etc.)\n"
            "  9. 3D or gaming-level work"
        ),
        "Multi-select. Numbers separated by commas — e.g. '1, 3, 5'.",
    ),
    "q5": (
        "Q5. Is there any specific software, website, or tool that must run on this device?",
        "(For example: Photoshop, Zoom, a school portal, a medical system. Type 'none' if you're not sure.)",
        "Just type what you need. The system understands product names and short phrases.",
    ),
    "q6": (
        "Q6. How many people will use this device, and what is your current internet / device situation?",
        None,
        "Example: 'four people will use it, we only have a phone right now'.",
    ),
    "q7": (
        "Q7. How soon do you need it?",
        (
            "  1. This week              (critical)\n"
            "  2. Within a month         (high)\n"
            "  3. 1 to 3 months          (medium)\n"
            "  4. Flexible               (low)"
        ),
        "Pick one number.",
    ),
    "q8": (
        "Q8. (Optional) A bit about your situation — you can skip any part.",
        (
            "  - Age range\n"
            "  - Year you arrived in Canada (if applicable)\n"
            "  - Employment status\n"
            "  - Any accessibility needs (vision, mobility, hearing)\n"
            "  - Have you received a device from us or a similar program before?"
        ),
        "Just write a short sentence covering whatever applies. Type 'skip' to leave it empty.",
    ),
}


def _ask(key: str, reader: Callable[[str], str], writer: Callable[[str], None]) -> str:
    prompt, options, helptext = QUESTIONS[key]
    while True:
        writer(prompt)
        if options:
            writer(options)
        answer = reader("> ").strip()
        if answer in {"?", "help"}:
            writer(f"(help) {helptext}")
            continue
        if not answer and key != "q3" and key != "q8":
            writer("Please type an answer, or '?' for help.")
            continue
        return answer


def run_intake(
    applicant_id: str | None = None,
    reader: Callable[[str], str] = input,
    writer: Callable[[str], None] = print,
    save_session: bool = True,
) -> Applicant:
    """Run the 8-question intake and return a validated Applicant.

    `reader` / `writer` are injectable for testing and for the demo
    transcript fixture.
    """
    applicant_id = applicant_id or f"app-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    writer("")
    writer("ASRA intake — 8 short questions.")
    writer("You can type '?' at any prompt to see help in simpler words.")
    writer("")

    raw: dict[str, str] = {}
    raw["q1"] = _ask("q1", reader, writer)
    writer(f"Got it: {raw['q1']}")
    writer("")

    raw["q2"] = _ask("q2", reader, writer)
    writer(f"Got it: {raw['q2']}")
    writer("")

    # Q3 only if Q2 included option 1 (school)
    if "1" in [c.strip() for c in raw["q2"].replace(";", ",").split(",")]:
        raw["q3"] = _ask("q3", reader, writer)
        writer(f"Got it: {raw['q3']}")
        writer("")
    else:
        raw["q3"] = ""

    raw["q4"] = _ask("q4", reader, writer)
    writer(f"Got it: {raw['q4']}")
    writer("")

    raw["q5"] = _ask("q5", reader, writer)
    writer(f"Got it: {raw['q5']}")
    writer("")

    raw["q6"] = _ask("q6", reader, writer)
    writer(f"Got it: {raw['q6']}")
    writer("")

    raw["q7"] = _ask("q7", reader, writer)
    writer(f"Got it: {raw['q7']}")
    writer("")

    q8 = _ask("q8", reader, writer)
    raw["q8"] = "" if q8.strip().lower() == "skip" else q8
    writer(f"Got it: {raw['q8'] or '(skipped)'}")
    writer("")

    # Send to the LLM (or heuristic fallback).
    writer("Parsing your answers...")
    intake_answers: IntakeAnswers = llm.parse_intake(raw)

    # One targeted follow-up if Q2 included School but we couldn't pick A1/A2/A3.
    if any(c in intake_answers.purpose for c in (Category.A1, Category.A2, Category.A3)):
        pass  # OK
    elif "1" in raw["q2"]:
        writer(
            "Quick follow-up: was the student in K-grade 6, grades 8-12, or post-secondary?"
        )
        follow = reader("> ").strip().lower()
        if "k" in follow or "6" in follow or "elementary" in follow:
            intake_answers.purpose.append(Category.A1)
        elif "high" in follow or "8" in follow or "10" in follow or "12" in follow:
            intake_answers.purpose.append(Category.A2)
        else:
            intake_answers.purpose.append(Category.A3)

    applicant = Applicant(
        applicant_id=applicant_id,
        intake=intake_answers,
        submitted_at=datetime.now().date(),
    )

    if save_session:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)
        path = SESSION_DIR / f"{applicant_id}.json"
        path.write_text(applicant.model_dump_json(indent=2))
        writer(f"(Saved intake to {path})")
        writer("")

    return applicant
