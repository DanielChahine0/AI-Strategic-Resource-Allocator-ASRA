"""Click-based CLI for the ASRA RAG matcher.

The only command is `ingest`, which embeds kb/ into the local Chroma store
(used by run.sh to build the vector store on first launch). The legacy
`match` / `intake` commands were removed in the Phase-5 simplification — the
simplified allocator is reached via the API (`/allocate`, `/batch`, `/impact`).
"""
from __future__ import annotations

import click
from dotenv import load_dotenv

# Load .env at import time so GEMINI_API_KEY (and friends) are available
# to every subsystem the CLI invokes.
load_dotenv()

from .rag import ingest as ingest_mod  # noqa: E402


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


if __name__ == "__main__":
    main()
