"""Ledger ingestion CLI.

Each stage is resumable and idempotent and writes ``data/stats/<stage>.json``
(docs/SPEC.md section 4). Heavy imports (sentence-transformers,
elasticsearch) are done inside the commands so ``--help`` stays fast.
"""

from __future__ import annotations

import typer

from ingest.config import get_settings

app = typer.Typer(help="Ledger ingestion pipeline", no_args_is_help=True)

_SUBSET = typer.Option("dev", "--subset", help="'dev' (deterministic sample) or 'full'")


def _emit(stats: object) -> None:
    summary = getattr(stats, "summary", None)
    if callable(summary):
        typer.echo(summary())


@app.command()
def download(
    force: bool = typer.Option(False, "--force", help="Re-download and re-extract."),
    subset: str = _SUBSET,
    prune_archive: bool = typer.Option(
        False, "--prune-archive", help="Delete the .tar.gz after a successful extract."
    ),
) -> None:
    """Fetch + checksum + extract the Enron corpus into data/raw/."""
    from ingest.download import download as run_download

    settings = get_settings()
    stats = run_download(settings, force=force, subset=subset, prune_archive=prune_archive)
    stats.write(settings.stats_dir)
    _emit(stats)


@app.command()
def parse(subset: str = _SUBSET) -> None:
    """Parse maildir messages with the email stdlib into parsed.jsonl."""
    from ingest import parse as parse_stage

    settings = get_settings()
    stats = parse_stage.run(
        settings.maildir, settings.parsed_path, subset, settings.dev_subset_size
    )
    stats.write(settings.stats_dir)
    _emit(stats)


@app.command()
def normalise() -> None:
    """Lowercase/dedupe addresses and assign person_id."""
    from ingest import normalise as normalise_stage

    settings = get_settings()
    stats = normalise_stage.run(settings.parsed_path, settings.normalised_path)
    stats.write(settings.stats_dir)
    _emit(stats)


@app.command()
def dedupe() -> None:
    """Collapse cross-mailbox duplicates into one canonical document."""
    from ingest import dedupe as dedupe_stage

    settings = get_settings()
    stats = dedupe_stage.run(settings.normalised_path, settings.deduped_path)
    stats.write(settings.stats_dir)
    _emit(stats)


@app.command()
def thread() -> None:
    """Assign thread_id from reply headers with a subject fallback."""
    from ingest import thread as thread_stage

    settings = get_settings()
    stats = thread_stage.run(settings.deduped_path, settings.threaded_path)
    stats.write(settings.stats_dir)
    _emit(stats)


@app.command()
def embed() -> None:
    """Chunk bodies and compute vectors in batches (resumable)."""
    from ingest import embed as embed_stage

    settings = get_settings()
    stats = embed_stage.run(settings.threaded_path, settings.embedded_path, settings)
    stats.write(settings.stats_dir)
    _emit(stats)


@app.command()
def index() -> None:
    """Bulk into the versioned index; flip the alias after count + smoke query."""
    from ingest import index as index_stage
    from ingest.es import make_client

    settings = get_settings()
    es = make_client(settings)
    try:
        stats = index_stage.run(
            es,
            settings.embedded_path,
            settings.mappings_path,
            settings.index_name,
            settings.emails_alias,
        )
    finally:
        es.close()
    stats.write(settings.stats_dir)
    _emit(stats)


@app.command()
def run(subset: str = _SUBSET) -> None:
    """Run every stage end to end."""
    download(subset=subset)
    parse(subset=subset)
    normalise()
    dedupe()
    thread()
    embed()
    index()


if __name__ == "__main__":
    app()
