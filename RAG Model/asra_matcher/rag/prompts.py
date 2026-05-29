"""Prompt templates for the three RAG-augmented LLM tasks."""
from __future__ import annotations

from ..models import Application, Device, RagContext


SYSTEM_BOILERPLATE = (
    "You are an allocation assistant for Let's Get Together. Answer ONLY using "
    "the provided context. If the context does not contain enough information "
    "to answer confidently, respond with "
    "{\"abstain\": true, \"reason\": \"...\", \"follow_up_question\": \"...\"}. "
    "Cite the source filename for every claim. Do not use outside knowledge."
)


def tier_recommendation_prompt(app: Application, ctx: RagContext) -> tuple[str, str]:
    """Returns (system, user). For A3 / C — RAG decides which tiers are allowed."""
    user = (
        "TASK: Recommend the most appropriate computer tier (T1, T2, or T3) for the "
        "applicant below, considering the category guidance, tier definitions, "
        "software capability matrix, and past decisions provided in CONTEXT.\n\n"
        f"APPLICANT_CATEGORY: {app.category.value}\n"
        f"A3_SUB_TRACK: {app.intake.a3_subtrack.value if app.intake.a3_subtrack else 'n/a'}\n"
        f"MAIN_USAGE: {app.intake.main_usage}\n"
        f"SOFTWARE_NEEDED: {', '.join(app.intake.software_needed) or 'none stated'}\n"
        f"SHARED_USER_COUNT: {app.intake.shared_user_count}\n"
        f"URGENCY: {app.intake.urgency.value}\n\n"
        "CONTEXT (retrieved knowledge base chunks):\n"
        f"{ctx.render()}\n\n"
        "Respond ONLY with JSON:\n"
        "{\n"
        '  "recommended_tier": "T1" | "T2" | "T3",\n'
        '  "rationale": "<2-3 sentences citing source filenames>",\n'
        '  "citations": ["<source_path>", ...],\n'
        '  "confidence": 0.0 to 1.0\n'
        "}\n"
        "If you cannot decide from the context alone, return "
        "{\"abstain\": true, \"reason\": \"...\", \"follow_up_question\": \"...\"}."
    )
    return SYSTEM_BOILERPLATE, user


def explanation_prompt(app: Application, devices: list[Device], ctx: RagContext) -> tuple[str, str]:
    """For each top device, 2–3 sentences explaining the match."""
    devices_block = "\n".join(
        f"- device_id={d.id} item_type={d.item_type.value} "
        f"tier={d.tier.value if d.tier else 'n/a'} condition={d.condition} "
        f"specs={d.specs}"
        for d in devices
    )
    user = (
        "TASK: Write 2–3 sentence explanations for EACH listed device, explaining why "
        "it is a good fit for the applicant below. Cite source filenames from CONTEXT. "
        "Do NOT change the ordering — you are explaining, not ranking.\n\n"
        f"APPLICANT_CATEGORY: {app.category.value}\n"
        f"MAIN_USAGE: {app.intake.main_usage}\n"
        f"SOFTWARE_NEEDED: {', '.join(app.intake.software_needed) or 'none stated'}\n"
        f"URGENCY: {app.intake.urgency.value}\n\n"
        f"DEVICES:\n{devices_block}\n\n"
        "CONTEXT:\n"
        f"{ctx.render()}\n\n"
        "Respond ONLY with JSON:\n"
        "{\n"
        '  "explanations": [\n'
        '    {"device_id": "...", "explanation": "...", "citations": ["..."]}, ...\n'
        "  ]\n"
        "}\n"
    )
    return SYSTEM_BOILERPLATE, user


def intake_parse_prompt(raw_answers: dict, ctx: RagContext) -> tuple[str, str]:
    """Parse free-text intake answers into the IntakeAnswers schema.

    The output shape is enforced via a native ``response_schema`` on the
    generation call (see ``llm._IntakeParseEnvelope``), so the full
    IntakeAnswers JSON-schema is intentionally NOT inlined here — that block was
    ~424 redundant input tokens re-sent on every call.
    """
    user = (
        "TASK: Parse the raw free-text intake answers below into the parsed "
        "object. Use the retrieved CONTEXT to disambiguate category mapping and "
        "software references. Leave unknown fields null/empty. Populate "
        "`citations` with the source filenames that informed inferred fields, "
        "and `uncertain_fields` with the names of any fields you were unsure "
        "about.\n\n"
        f"RAW_ANSWERS:\n{raw_answers}\n\n"
        "CONTEXT:\n"
        f"{ctx.render()}\n"
    )
    return SYSTEM_BOILERPLATE, user
