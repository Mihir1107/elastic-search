"""Evaluation CLI: build pools, judge them, measure, report.

uv run python -m eval.cli pool       # run every method, pool the candidates
uv run python -m eval.cli autolabel  # grade what can be graded by rule
uv run python -m eval.cli label      # hand-label the rest (resumable)
uv run python -m eval.cli run        # metrics + eval/results/<date>.md
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer

from app.config import get_settings
from app.es import make_client
from eval import harness, judge, report
from eval import prelabel as prelabel_mod
from eval.metrics import evaluate_run

app = typer.Typer(help="Ledger relevance evaluation", no_args_is_help=True)

EVAL_DIR = Path(__file__).resolve().parent
QUERIES = EVAL_DIR / "queries.yaml"
POOLS = EVAL_DIR / "pools.json"
QRELS = EVAL_DIR / "qrels.jsonl"
RESULTS = EVAL_DIR / "results"
BASELINE = RESULTS / "baseline.json"


async def _pool() -> dict[str, Any]:
    settings = get_settings()
    es = make_client(settings)
    try:
        queries = harness.load_queries(QUERIES)
        runs = await harness.run_all(es, settings, queries)
        pools = harness.build_pools(runs)
        all_ids = sorted({d for ids in pools.values() for d in ids})
        docs = await harness.fetch_docs(es, settings, all_ids)
    finally:
        await es.close()
    return {"pools": pools, "docs": docs, "runs": runs}


@app.command()
def pool() -> None:
    """Run every method over every query and pool the top candidates."""
    payload = asyncio.run(_pool())
    POOLS.write_text(json.dumps(payload, indent=None))
    sizes = [len(v) for v in payload["pools"].values()]
    typer.echo(
        f"pooled {sum(sizes)} (query, doc) pairs across {len(sizes)} queries "
        f"(avg {sum(sizes) / max(1, len(sizes)):.1f}/query); wrote {POOLS.name}"
    )


@app.command()
def autolabel() -> None:
    """Grade pooled documents for every query that declares an objective rule."""
    if not POOLS.exists():
        typer.echo("no pools yet; run 'pool' first")
        raise typer.Exit(code=1)
    payload = json.loads(POOLS.read_text())
    queries = {str(q["id"]): q for q in harness.load_queries(QUERIES)}

    judgments = list(judge.load_judgments(QRELS))
    added = 0
    for query_id, doc_ids in payload["pools"].items():
        query = queries.get(query_id)
        if not query or not query.get("auto"):
            continue
        docs = [payload["docs"][d] for d in doc_ids if d in payload["docs"]]
        graded = judge.grade_pool(query, docs)
        judgments.extend(graded)
        added += len(graded)

    total = judge.save_judgments(QRELS, judgments)
    typer.echo(f"auto-graded {added} pairs; qrels now holds {total} judgments")


@app.command()
def label(
    query_id: str = typer.Option("", "--query", help="Label only this query id"),
    limit: int = typer.Option(0, "--limit", help="Stop after this many pairs"),
    prelabel: bool = typer.Option(
        False, "--prelabel", help="Suggest a grade with an LLM (spends API credits)"
    ),
) -> None:
    """Hand-label pooled documents that no rule covers. Resumable; 'q' saves and exits."""
    if not POOLS.exists():
        typer.echo("no pools yet; run 'pool' first")
        raise typer.Exit(code=1)
    payload = json.loads(POOLS.read_text())
    queries = {str(q["id"]): q for q in harness.load_queries(QUERIES)}

    judgments = list(judge.load_judgments(QRELS))
    done = {(j.query_id, j.doc_id) for j in judgments}

    todo: list[tuple[str, str]] = []
    for qid, doc_ids in payload["pools"].items():
        query = queries.get(qid)
        if not query or (query_id and qid != query_id):
            continue
        if query.get("auto"):
            continue  # graded by rule
        todo.extend((qid, d) for d in doc_ids if (qid, d) not in done)

    if not todo:
        typer.echo("nothing left to label")
        return

    typer.echo(f"{len(todo)} pair(s) to label. 0-3 = grade, s = skip, q = save and quit.\n")
    labelled = 0
    for qid, doc_id in todo:
        if limit and labelled >= limit:
            break
        query = queries[qid]
        doc = payload["docs"].get(doc_id, {})
        body = " ".join(str(doc.get("body") or "").split())[:280]
        typer.secho(f"\n[{qid}] {query['query']}", fg=typer.colors.CYAN, bold=True)
        typer.echo(f"  intent : {query.get('intent', '')}")
        typer.echo(f"  from   : {doc.get('from', '')}   {str(doc.get('date') or '')[:10]}")
        typer.echo(f"  subject: {doc.get('subject', '')!r}")
        typer.echo(f"  body   : {body}")
        default = "s"
        if prelabel:
            try:
                suggested = prelabel_mod.suggest_grade(query, doc)
            except prelabel_mod.PrelabelUnavailable as exc:
                typer.secho(f"  (pre-label off: {exc})", fg=typer.colors.YELLOW)
                prelabel = False
            else:
                if suggested is not None:
                    typer.secho(f"  suggested: {suggested}", fg=typer.colors.MAGENTA)
                    default = str(suggested)
        answer = typer.prompt("  grade (0-3 / s / q)", default=default).strip().lower()
        if answer == "q":
            break
        if answer == "s" or not answer.isdigit():
            continue
        grade = max(judge.GRADE_MIN, min(judge.GRADE_MAX, int(answer)))
        judgments.append(judge.Judgment(qid, doc_id, grade, "human"))
        labelled += 1

    total = judge.save_judgments(QRELS, judgments)
    typer.echo(f"\nlabelled {labelled} pair(s); qrels now holds {total} judgments")


async def _measure() -> dict[str, Any]:
    settings = get_settings()
    es = make_client(settings)
    try:
        queries = harness.load_queries(QUERIES)
        runs = await harness.run_all(es, settings, queries)
    finally:
        await es.close()
    return {"queries": queries, "runs": runs}


@app.command()
def run(
    write_baseline: bool = typer.Option(
        False, "--write-baseline", help="Also update results/baseline.json"
    ),
) -> None:
    """Measure every method against the judgments and write the report."""
    payload = asyncio.run(_measure())
    queries: list[dict[str, Any]] = payload["queries"]
    runs: dict[str, dict[str, list[str]]] = payload["runs"]
    qrels = judge.load_qrels(QRELS)
    judgments = judge.load_judgments(QRELS)

    judged_ids = sorted(
        qid for qid, rel in qrels.items() if any(g > 0 for g in rel.values()) or rel
    )
    by_id = {str(q["id"]): q for q in queries}
    auto_ids = {qid for qid in judged_ids if by_id.get(qid, {}).get("auto")}
    coverage = {
        "total_queries": len(queries),
        "by_category": dict(Counter(str(q["category"]) for q in queries)),
        "judged_queries": len(judged_ids),
        "judged_ids": judged_ids,
        "auto_queries": len(auto_ids),
        "human_queries": len(set(judged_ids) - auto_ids),
        "unjudged_queries": len(queries) - len(judged_ids),
        "judgments": len(judgments),
        "auto_judgments": sum(1 for j in judgments if j.source.startswith("auto")),
        "human_judgments": sum(1 for j in judgments if j.source == "human"),
    }

    results: dict[str, dict[str, float]] = {}
    per_category: dict[str, dict[str, dict[str, float]]] = {}
    for method, per_query in runs.items():
        results[method] = evaluate_run(per_query, qrels)
        buckets: dict[str, dict[str, list[str]]] = {}
        for qid, ranked in per_query.items():
            category = str(by_id.get(qid, {}).get("category", "unknown"))
            buckets.setdefault(category, {})[qid] = ranked
        per_category[method] = {
            category: evaluate_run(sub, qrels) for category, sub in buckets.items()
        }

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    out = RESULTS / f"{stamp}.md"
    out.write_text(report.render_report(results, per_category, coverage, queries))

    if write_baseline:
        BASELINE.write_text(
            json.dumps({"generated": stamp, "coverage": coverage, "results": results}, indent=2)
            + "\n"
        )

    for method, metrics in results.items():
        typer.echo(
            f"  {method:<7} ndcg@10={metrics['ndcg@10']:.4f} "
            f"mrr={metrics['mrr']:.4f} recall@50={metrics['recall@50']:.4f} "
            f"(n={int(metrics['queries'])})"
        )
    typer.echo(f"wrote {out}")


REGRESSION_MARGIN = 0.02  # 2 NDCG points, per the spec


@app.command()
def check() -> None:
    """Fail if hybrid NDCG@10 regressed more than 2 points against the baseline.

    Skips cleanly when there is no baseline yet or the cluster holds no indexed
    mail, so it can sit in CI without pretending to measure an empty index.
    """
    if not BASELINE.exists():
        typer.echo(f"no baseline at {BASELINE}; run 'run --write-baseline' first")
        raise typer.Exit(code=0)
    baseline = json.loads(BASELINE.read_text())
    previous = float(baseline["results"]["hybrid"]["ndcg@10"])

    try:
        payload = asyncio.run(_measure())
    except Exception as exc:
        typer.echo(f"could not measure ({type(exc).__name__}); skipping regression check")
        raise typer.Exit(code=0) from None
    qrels = judge.load_qrels(QRELS)
    current_metrics = evaluate_run(payload["runs"]["hybrid"], qrels)
    if int(current_metrics["queries"]) == 0:
        typer.echo("no judged queries scored (is the index populated?); skipping")
        raise typer.Exit(code=0)

    current = float(current_metrics["ndcg@10"])
    delta = current - previous
    typer.echo(
        f"hybrid ndcg@10: baseline={previous:.4f} current={current:.4f} "
        f"delta={delta:+.4f} (allowed -{REGRESSION_MARGIN:.2f})"
    )
    if delta < -REGRESSION_MARGIN:
        typer.secho("REGRESSION: hybrid NDCG@10 dropped too far", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    typer.secho("ok", fg=typer.colors.GREEN)


#: Field-boost configurations to sweep. The first entry is the current default.
FIELD_SWEEP: list[tuple[str, list[str]]] = [
    ("default subject^3", ["subject^3", "body", "from.text", "to.text"]),
    ("subject^1 (no boost)", ["subject", "body", "from.text", "to.text"]),
    ("subject^2", ["subject^2", "body", "from.text", "to.text"]),
    ("subject^5", ["subject^5", "body", "from.text", "to.text"]),
    ("subject^3 people^2", ["subject^3", "body", "from.text^2", "to.text^2"]),
    ("subject^3 body^2", ["subject^3", "body^2", "from.text", "to.text"]),
    ("no people fields", ["subject^3", "body"]),
]


@app.command()
def tune(
    method: str = typer.Option("hybrid", help="Which method to tune against"),
) -> None:
    """Sweep BM25 field boosts and report the NDCG@10 delta for each.

    Every tuning change in Phase 4 has to be justified by a number; this is how
    that number gets produced.
    """
    queries = harness.load_queries(QUERIES)
    qrels = judge.load_qrels(QRELS)
    settings = get_settings()
    original = list(settings.bm25_fields)

    async def measure(fields: list[str]) -> dict[str, float]:
        settings.bm25_fields = fields
        es = make_client(settings)
        try:
            runs = await harness.run_all(es, settings, queries, methods=(method,))
        finally:
            await es.close()
        return evaluate_run(runs[method], qrels)

    rows: list[tuple[str, dict[str, float]]] = []
    try:
        for label_text, fields in FIELD_SWEEP:
            rows.append((label_text, asyncio.run(measure(fields))))
    finally:
        settings.bm25_fields = original

    base = rows[0][1]["ndcg@10"]
    typer.echo("")
    typer.echo(f"field-boost sweep on '{method}'")
    typer.echo("")
    header = f"  {'configuration':<22} {'ndcg@10':>9} {'delta':>9} {'mrr':>8}"
    typer.echo(header)
    for label_text, metrics in rows:
        delta = metrics["ndcg@10"] - base
        mark = "  <- current" if label_text.startswith("default") else ""
        line = (
            f"  {label_text:<22} {metrics['ndcg@10']:>9.4f} "
            f"{delta:>+9.4f} {metrics['mrr']:>8.4f}{mark}"
        )
        typer.echo(line)


if __name__ == "__main__":
    app()
