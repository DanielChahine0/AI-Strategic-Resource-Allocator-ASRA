"""Click-based CLI for ASRA matcher."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

# Load .env at import time so GEMINI_API_KEY (and friends) are available
# to every subsystem the CLI invokes.
load_dotenv()

from . import engine as engine_mod  # noqa: E402
from . import intake as intake_mod  # noqa: E402
from .models import Applicant, Device, FinalMatchResult  # noqa: E402
from .rag import ingest as ingest_mod  # noqa: E402


def _load_inventory(path: str) -> list[Device]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise click.ClickException("inventory file must be a JSON list of devices")
    return [Device.model_validate(d) for d in raw]


def _load_applicant(path: str) -> Applicant:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return Applicant.model_validate(raw)


def _render_result(result: FinalMatchResult) -> str:
    out = []
    out.append(f"\n=== Match Result for applicant {result.applicant_id} ===")
    out.append(
        f"Chosen application: category {result.chosen_application.category.value}"
    )
    if result.discarded_applications:
        out.append(
            "Discarded applications: "
            + ", ".join(a.category.value for a in result.discarded_applications)
        )
    if result.notes:
        out.append("Notes:")
        for n in result.notes:
            out.append(f"  - {n}")
    if not result.top_matches:
        out.append("No matches found.")
        return "\n".join(out)
    out.append("\nTop matches:")
    for i, m in enumerate(result.top_matches, 1):
        b = m.breakdown
        out.append(
            f"  #{i} {m.device.id} "
            f"(item={m.device.item_type.value} tier={m.device.tier.value if m.device.tier else 'n/a'} "
            f"condition={m.device.condition}/5 avail={m.device.available_from})"
        )
        out.append(
            f"      composite={b.composite:.3f} "
            f"priority={b.priority:.2f} timing={b.timing:.2f} "
            f"condition={b.condition:.2f} efficiency={b.efficiency:.2f}"
        )
        if m.explanation:
            out.append(f"      explanation: {m.explanation}")
        if m.citations:
            out.append("      citations: " + ", ".join(m.citations))
    if result.retrieval_trace:
        out.append("\nRetrieval trace:")
        for task, chunks in result.retrieval_trace.items():
            out.append(f"  [{task}]")
            for c in chunks:
                out.append(
                    f"    - {c.source_path} (sim={c.similarity:.3f}, ns={c.namespace})"
                )
    return "\n".join(out)


@click.group()
def main() -> None:
    """ASRA matcher CLI."""


@main.command()
@click.option("--rebuild", is_flag=True, help="Wipe collections before ingesting.")
def ingest(rebuild: bool) -> None:
    """Embed kb/ into the local Chroma store."""
    counts = ingest_mod.ingest(rebuild=rebuild)
    click.echo("Ingest complete:")
    for ns, n in counts.items():
        click.echo(f"  {ns}: {n} chunks")


@main.command()
@click.option(
    "--inventory",
    "inventory_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to inventory JSON.",
)
def intake(inventory_path: str) -> None:
    """Run the interactive 7-question intake, then match against inventory."""
    inv = _load_inventory(inventory_path)
    applicant, _raw = intake_mod.run_intake()
    result = engine_mod.match(applicant, inv)
    click.echo(_render_result(result))


@main.command()
@click.argument("applicant_path", type=click.Path(exists=True))
@click.option(
    "--inventory",
    "inventory_path",
    required=True,
    type=click.Path(exists=True),
    help="Path to inventory JSON.",
)
def match(applicant_path: str, inventory_path: str) -> None:
    """Run the engine against a pre-built Applicant JSON."""
    applicant = _load_applicant(applicant_path)
    inv = _load_inventory(inventory_path)
    result = engine_mod.match(applicant, inv)
    click.echo(_render_result(result))


if __name__ == "__main__":
    main()
