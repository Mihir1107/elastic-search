"""``uv run python -m ops.snapshots.cli snapshot|restore|list``."""

from __future__ import annotations

from datetime import UTC, datetime

import typer

from ingest.config import get_settings
from ingest.es import make_client
from ops.snapshots.repo import (
    create,
    ensure_repository,
    next_version,
    resolve_alias,
    restore_as,
)

app = typer.Typer(help="Snapshot and restore", no_args_is_help=True)

REPOSITORY = "ledger-snapshots"
#: Matches `path.repo` and the shared `snapshots` volume in docker-compose.yml.
LOCATION = "/snapshots"


@app.callback()
def _main() -> None:
    """Keeps the subcommands addressable."""


@app.command()
def snapshot(
    name: str = typer.Option("", help="Snapshot name (default: emails-<UTC timestamp>)."),
    repository: str = typer.Option(REPOSITORY, "--repo"),
) -> None:
    """Snapshot the index currently behind the `emails` alias."""
    settings = get_settings()
    es = make_client(settings)
    try:
        if ensure_repository(es, repository, LOCATION):
            typer.echo(f"registered repository {repository!r} at {LOCATION}")
        index = resolve_alias(es, settings.emails_alias)
        snapshot_name = name or f"{index}-{datetime.now(UTC).strftime('%Y%m%dt%H%M%S')}"
        typer.echo(f"snapshotting {index} as {snapshot_name} ...")
        info = create(es, repository, snapshot_name, index)
    finally:
        es.close()

    typer.echo(
        f"{info.state}: {', '.join(info.indices)} "
        f"({info.shards_total} shards, {info.shards_failed} failed) in {info.duration_ms} ms"
    )
    if info.state != "SUCCESS" or info.shards_failed:
        raise typer.Exit(code=1)


@app.command(name="list")
def list_snapshots(repository: str = typer.Option(REPOSITORY, "--repo")) -> None:
    """Show what is in the repository."""
    es = make_client()
    try:
        ensure_repository(es, repository, LOCATION)
        body = es.snapshot.get(repository=repository, snapshot="*").body
    finally:
        es.close()
    for snap in body.get("snapshots", []):
        typer.echo(
            f"{snap['snapshot']:<40} {snap['state']:<10} "
            f"{', '.join(snap.get('indices', []))}  {snap.get('start_time', '')}"
        )


@app.command()
def restore(
    snapshot_name: str = typer.Argument(..., help="Snapshot to restore."),
    into: str = typer.Option("", help="Target index (default: the next free -vN)."),
    repository: str = typer.Option(REPOSITORY, "--repo"),
) -> None:
    """Restore into a NEW index version. Never touches the serving index."""
    es = make_client()
    try:
        body = es.snapshot.get(repository=repository, snapshot=snapshot_name).body
        source = body["snapshots"][0]["indices"][0]
        # Only the sibling versions matter for picking a free name, and listing
        # "*" drags in system indices (and their deprecation warning).
        base = source.rsplit("-v", 1)[0]
        existing = sorted(es.indices.get(index=f"{base}-v*", ignore_unavailable=True).body)
        target = into or next_version(source, existing)
        typer.echo(f"restoring {source} from {snapshot_name} into {target} ...")
        result = restore_as(es, repository, snapshot_name, source, target)
    finally:
        es.close()

    typer.echo(
        f"restored {result['target_index']}: {result['docs']} docs, "
        f"health {result['health']}, aliases {result['aliases'] or 'none'}"
    )
    typer.echo(
        "The `emails` alias was NOT moved. Verify the restored index, then flip the "
        "alias deliberately."
    )


if __name__ == "__main__":
    app()
