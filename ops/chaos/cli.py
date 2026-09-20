"""``uv run python -m ops.chaos.cli run`` -- the HA demonstration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from app.config import get_settings
from ops.bench.runner import BenchConfig, load_queries
from ops.chaos.cluster import ClusterWatcher, busiest_primary_node, container_for_node
from ops.chaos.report import write as write_report
from ops.chaos.runner import ChaosConfig, run_chaos

app = typer.Typer(help="Chaos / HA demonstration", no_args_is_help=True)

DEFAULT_QUERIES = Path("eval/queries.yaml")
DEFAULT_OUT = Path("ops/results")


@app.callback()
def _main() -> None:
    """Keeps ``run`` addressable as a subcommand."""


@app.command()
def run(
    container: str = typer.Option(
        "auto", help="Container to kill, or 'auto' for the node holding the most primaries."
    ),
    base_url: str = typer.Option("http://127.0.0.1:8000", help="Running search API."),
    concurrency: int = typer.Option(4, min=1),
    before_s: float = typer.Option(20.0, help="Seconds of green-state load before the kill."),
    during_s: float = typer.Option(40.0, help="Seconds of load while the node is down."),
    after_s: float = typer.Option(90.0, help="Seconds to wait for recovery after restart."),
    queries_path: Path = typer.Option(DEFAULT_QUERIES, "--queries", exists=True),
    out_dir: Path = typer.Option(DEFAULT_OUT, "--out"),
    label: str = typer.Option("chaos", help="Output basename under --out."),
) -> None:
    """Kill one node mid-load and report success rate, promotion and recovery."""
    settings = get_settings()
    bench = BenchConfig(base_url=base_url, concurrency=concurrency)
    chaos = ChaosConfig(container=container, before_s=before_s, during_s=during_s, after_s=after_s)
    watcher = ClusterWatcher(
        hosts=settings.es_hosts,
        username=settings.es_username,
        password=settings.es_password,
        ca_cert=settings.es_ca_cert,
    )
    if len(watcher.hosts) < 2:
        typer.secho(
            "ES_HOST lists one node. Killing it fails every request; list all published "
            "nodes (see .env.example) before running chaos.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    if container == "auto":
        rows = watcher.shards(chaos.index_pattern)
        node = busiest_primary_node(rows)
        container = container_for_node(node)
        chaos = ChaosConfig(
            container=container, before_s=before_s, during_s=during_s, after_s=after_s
        )
        typer.echo(f"target: node {node} ({container}) holds the most primaries")

    queries = load_queries(queries_path)
    typer.echo(
        f"killing {container} after {before_s:.0f}s; "
        f"{during_s:.0f}s down, up to {after_s:.0f}s recovery"
    )
    result = asyncio.run(run_chaos(bench, chaos, queries, watcher))
    json_path, md_path = write_report(bench, chaos, result, out_dir, label)

    overall = result.overall
    gate = "PASS" if overall.failed == 0 else "FAIL"
    typer.echo(
        f"[{gate}] {overall.requests} requests, {overall.failed} failed "
        f"({overall.success_rate * 100:.2f}% ok)"
    )
    for name, summary in result.buckets.items():
        typer.echo(
            f"  {name:<7} n={summary.requests:<5} failed={summary.failed:<3} "
            f"p50={summary.wall.get('p50', 0):.1f}ms p95={summary.wall.get('p95', 0):.1f}ms"
        )
    typer.echo("  health: " + " -> ".join(status for _, status in result.transitions))
    typer.echo(f"wrote {md_path} and {json_path}")


if __name__ == "__main__":
    app()
