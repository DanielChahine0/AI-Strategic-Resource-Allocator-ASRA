"""Interactive 7-question terminal intake.

ESL-friendly. Allows ``?`` at any prompt to re-explain. Free-text answers are
RAG-parsed downstream by :func:`asra_matcher.llm.parse_intake`.
"""
from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO

from . import llm as llm_mod
from .models import Applicant, IntakeAnswers
from .taxonomy import A3SubTrack, Category


QUESTIONS = {
    "q1": {
        "prompt": "Q1. Who needs the computer?",
        "options": [
            "1. You",
            "2. Your child or someone you take care of",
            "3. Shared in your household",
            "4. Someone else (please tell us who)",
        ],
        "help": (
            "Tell us who will use this computer. You can pick a number "
            "(1, 2, 3, 4) or just describe in your own words."
        ),
    },
    "q2": {
        "prompt": "Q2. What do you need this for? (choose all that apply)",
        "options": [
            "1. School or learning",
            "2. Work or job searching",
            "3. Healthcare (appointments, portals, prescriptions)",
            "4. Personal use (staying connected, browsing)",
            "5. Settling in Canada (newcomer)",
            "6. Other (please describe)",
        ],
        "help": (
            "Choose all reasons that match — type the numbers separated by "
            "commas, like: 1, 3, 5. You can also describe in your own words."
        ),
    },
    "q2_school": {
        "prompt": "    What level?",
        "options": [
            "1. K to Grade 6",
            "2. Grade 8 through high school",
            "3. Post-secondary — please tell us the program name",
        ],
        "help": "Pick the school level. For post-secondary, share the program name.",
    },
    "q3": {
        "prompt": "Q3. What is the main usage? What will you do on the device most days?",
        "options": [
            "(For example: writing documents, video calls, programming, design, online classes.)"
        ],
        "help": "Describe what you'll use this device for day-to-day.",
    },
    "q4": {
        "prompt": "Q4. Is there any specific software, website, or tool that must run on this device?",
        "options": [
            "(For example: Photoshop, Zoom, a school portal, a medical system. Type 'none' if not sure.)"
        ],
        "help": (
            "List any apps, websites, or tools you must use. If you're unsure, type 'none'."
        ),
    },
    "q5": {
        "prompt": "Q5. How many people will share this device? (1 = just you)",
        "options": [],
        "help": "How many household members will use it? Type a number.",
    },
    "q6": {
        "prompt": "Q6. How soon do you need it?",
        "options": [
            "1. This week (critical)",
            "2. Within a month (high)",
            "3. 1 to 3 months (medium)",
            "4. Flexible (low)",
        ],
        "help": "How urgent is this for you? Pick a number.",
    },
    "q7": {
        "prompt": "Q7. What is your current access to technology?",
        "options": [
            "- Do you have internet where you'll use this device?",
            "- Do you currently have any computer, tablet, or phone?",
            "  (none / phone only / shared device / outdated device)",
        ],
        "help": (
            "Tell us about your internet access and what tech you already have. "
            "It helps us understand your situation."
        ),
    },
}


def _ask(qkey: str, *, in_stream: TextIO, out_stream: TextIO) -> str:
    q = QUESTIONS[qkey]
    while True:
        out_stream.write("\n" + q["prompt"] + "\n")
        for opt in q["options"]:
            out_stream.write("    " + opt + "\n")
        out_stream.write("> ")
        out_stream.flush()
        line = in_stream.readline()
        if not line:
            return ""
        ans = line.strip()
        if ans == "?":
            out_stream.write("\n[help] " + q["help"] + "\n")
            continue
        return ans


def run_intake(
    *,
    in_stream: Optional[TextIO] = None,
    out_stream: Optional[TextIO] = None,
    sessions_dir: Path | None = None,
    parser=None,
    applicant_id: Optional[str] = None,
) -> tuple[Applicant, dict]:
    """Run the 7-question interactive intake. Returns (Applicant, raw_answers)."""
    in_stream = in_stream or sys.stdin
    out_stream = out_stream or sys.stdout
    parser = parser or llm_mod.parse_intake
    applicant_id = applicant_id or f"appl-{uuid.uuid4().hex[:8]}"

    out_stream.write(
        "\n=== ASRA Intake ===\n"
        "We have 7 short questions. Type '?' at any time for help.\n"
    )

    raw: dict[str, str] = {}
    raw["q1"] = _ask("q1", in_stream=in_stream, out_stream=out_stream)
    raw["q2"] = _ask("q2", in_stream=in_stream, out_stream=out_stream)

    # Conditional school follow-up
    if _mentions_school(raw["q2"]):
        raw["q2_school"] = _ask("q2_school", in_stream=in_stream, out_stream=out_stream)
        if raw["q2_school"].strip().startswith("3"):
            out_stream.write("    Program name? > ")
            out_stream.flush()
            line = in_stream.readline()
            raw["q2_program"] = line.strip() if line else ""
    raw["q3"] = _ask("q3", in_stream=in_stream, out_stream=out_stream)
    raw["q4"] = _ask("q4", in_stream=in_stream, out_stream=out_stream)
    raw["q5"] = _ask("q5", in_stream=in_stream, out_stream=out_stream)
    raw["q6"] = _ask("q6", in_stream=in_stream, out_stream=out_stream)
    raw["q7"] = _ask("q7", in_stream=in_stream, out_stream=out_stream)

    # RAG-parse the answers
    parse_result = parser(raw, applicant_id=applicant_id)
    intake = parse_result.parsed

    # Apply A3 sub-track inference if applicable
    if Category.A3 in intake.purpose and intake.a3_subtrack is None:
        intake = intake.model_copy(
            update={
                "a3_subtrack": _infer_a3_subtrack(raw.get("q2_program", "") + " " + intake.main_usage),
                "a3_program_name": raw.get("q2_program") or intake.a3_program_name,
            }
        )

    applicant = Applicant(id=applicant_id, intake=intake)

    sessions_dir = sessions_dir or Path("./intake_sessions")
    sessions_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    session_path = sessions_dir / f"{ts}_{applicant_id}.json"
    session_path.write_text(
        json.dumps(
            {
                "applicant": applicant.model_dump(mode="json"),
                "raw_answers": raw,
                "citations": parse_result.citations,
                "uncertain_fields": parse_result.uncertain_fields,
                "fallback_used": parse_result.fallback_used,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    out_stream.write(
        f"\n[intake saved → {session_path}]\n"
        f"[purpose categories: {[c.value for c in intake.purpose]}]\n"
    )
    if parse_result.fallback_used:
        out_stream.write(
            "[note] LLM parser fell back to heuristic parsing. Review the saved intake.\n"
        )
    return applicant, raw


def _mentions_school(text: str) -> bool:
    if not text:
        return False
    s = text.lower()
    if "1" in re.findall(r"\b\d\b", s):
        return True
    return any(kw in s for kw in ("school", "learning", "student", "study", "education"))


def _infer_a3_subtrack(text: str) -> A3SubTrack | None:
    s = (text or "").lower()
    if any(kw in s for kw in ("software", "computer science", "cs ", "coding", "programming", "engineer")):
        return A3SubTrack.SOFTWARE_ENGINEERING
    if any(kw in s for kw in ("art", "design", "media", "music", "film", "animation")):
        return A3SubTrack.ARTS
    if any(kw in s for kw in ("biology", "chem", "physics", "math", "science", "nursing", "research")):
        return A3SubTrack.SCIENCE
    if any(kw in s for kw in ("business", "commerce", "accounting", "marketing", "mba", "finance")):
        return A3SubTrack.BUSINESS
    return None


# Imported late to keep the module's main API at top of file.
import re  # noqa: E402
