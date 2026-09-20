"""Ledger ingestion CLI (typer).

Phase 0 wires the command surface; each stage is implemented in Phase 1
(CLAUDE_CODE_KICKOFF.md §5). Every stage is designed to be resumable and
idempotent and to write ``data/stats/<stage>.json``.
"""

from __future__ import annotations

import typer

app = typer.Typer(help="Ledger ingestion pipeline", no_args_is_help=True)

_PHASE1 = "not implemented yet (arrives in Phase 1)"


def _todo(stage: str) -> None:
    typer.secho(f"[{stage}] {_PHASE1}", fg=typer.colors.YELLOW)
    raise typer.Exit(code=1)


@app.command()
def download() -> None:
    """Fetch + checksum + extract the Enron corpus into data/raw/."""
    _todo("download")


@app.command()
def parse() -> None:
    """Parse maildir messages with the email stdlib into parsed.jsonl."""
    _todo("parse")


@app.command()
def normalise() -> None:
    """Lowercase/dedupe addresses; assign person_id."""
    _todo("normalise")


@app.command()
def dedupe() -> None:
    """Collapse cross-mailbox duplicates into one canonical doc."""
    _todo("dedupe")


@app.command()
def thread() -> None:
    """Assign thread_id from Message-ID/In-Reply-To with a subject fallback."""
    _todo("thread")


@app.command()
def embed() -> None:
    """Chunk bodies and compute vectors in batches (resumable, overnight-safe)."""
    _todo("embed")


@app.command()
def index() -> None:
    """Bulk into the versioned index; flip the alias after count + smoke query."""
    _todo("index")


@app.command()
def run(
    subset: str = typer.Option("dev", help="'dev' (10k deterministic) or 'full'"),
) -> None:
    """Run every stage end to end."""
    _todo(f"run:{subset}")


if __name__ == "__main__":
    app()
