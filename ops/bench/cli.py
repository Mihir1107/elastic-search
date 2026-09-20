"""``uv run python -m ops.bench.cli run`` -- measure search latency."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
import typer

from ops.bench.report import write as write_report
from ops.bench.runner import BenchConfig, load_queries, run_bench, summarise

app = typer.Typer(help="Search latency benchmark", no_args_is_help=True)

DEFAULT_QUERIES = Path("eval/queries.yaml")
DEFAULT_OUT = Path("ops/results")


def _context(base_url: str) -> dict[str, Any]:
    """Record what was measured. A latency number without the corpus is noise."""
    try:
        health = httpx.get(f"{base_url}/health", timeout=10.0).json()
    except httpx.HTTPError as exc:
        return {"health_error": type(exc).__name__}
    return {
        "index": ",".join(health.get("active_index") or []) or "?",
        "docs": health.get("docs"),
        "elasticsearch": health.get("elasticsearch"),
        "license": health.get("license_tier"),
        "nodes": health.get("number_of_nodes"),
    }


@app.callback()
def _main() -> None:
    """Typer collapses a single-command app into a bare invocation; this keeps
    the ``run`` subcommand addressable so ``chaos`` can be added beside it."""


@app.command()
def run(
    base_url: str = typer.Option("http://127.0.0.1:8000", help="Running search API."),
    concurrency: int = typer.Option(4, min=1, help="Parallel in-flight requests."),
    iterations: int = typer.Option(5, min=1, help="Passes over the query set."),
    size: int | None = typer.Option(None, help="Results per page (default: API default)."),
    rerank: bool = typer.Option(False, help="Include the cross-encoder (gate excludes it)."),
    queries_path: Path = typer.Option(DEFAULT_QUERIES, "--queries", exists=True),
    out_dir: Path = typer.Option(DEFAULT_OUT, "--out"),
    label: str = typer.Option("bench", help="Output basename under --out."),
) -> None:
    """Fire the evaluation query set at the API and report p50/p95/p99."""
    cfg = BenchConfig(
        base_url=base_url, concurrency=concurrency, iterations=iterations, size=size, rerank=rerank
    )
    queries = load_queries(queries_path)
    context = _context(base_url)

    samples = asyncio.run(run_bench(cfg, queries))
    summary = summarise(samples)
    json_path, md_path = write_report(cfg, summary, out_dir, context=context, label=label)

    typer.echo(
        f"{summary.requests} requests, {summary.failed} failed "
        f"({summary.success_rate * 100:.1f}% ok) over {len(queries)} queries "
        f"on {context.get('index')} ({context.get('docs')} docs)"
    )
    wall = summary.wall
    typer.echo(
        f"  wall     p50={wall['p50']:.1f}ms p95={wall['p95']:.1f}ms p99={wall['p99']:.1f}ms"
    )
    for stage, dist in summary.stages.items():
        if dist["p50"] or dist["p95"]:
            typer.echo(f"  {stage:<10} p50={dist['p50']:.1f}ms p95={dist['p95']:.1f}ms")
    typer.echo(f"wrote {md_path} and {json_path}")


if __name__ == "__main__":
    app()
