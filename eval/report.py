"""Render the evaluation report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

METRIC_ORDER = ("ndcg@10", "mrr", "recall@50")


def _fmt(value: float) -> str:
    return f"{value:.4f}"


def render_report(
    results: Mapping[str, Mapping[str, float]],
    per_category: Mapping[str, Mapping[str, Mapping[str, float]]],
    coverage: Mapping[str, Any],
    queries: Sequence[Mapping[str, Any]],
) -> str:
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Relevance evaluation",
        "",
        f"Generated {now}",
        "",
        "## Judgment coverage",
        "",
        f"- Query set: **{coverage['total_queries']}** queries "
        f"({', '.join(f'{k} {v}' for k, v in sorted(coverage['by_category'].items()))})",
        f"- Judged queries: **{coverage['judged_queries']}**"
        f" (auto-graded by rule: {coverage['auto_queries']},"
        f" human-labelled: {coverage['human_queries']})",
        f"- Unjudged queries: **{coverage['unjudged_queries']}**"
        " — excluded from the means below, never scored as zero",
        f"- Judgments: {coverage['judgments']}"
        f" ({coverage['auto_judgments']} auto, {coverage['human_judgments']} human)",
        "",
        "Auto-graded judgments come from objective rules (a required phrase, sender or date",
        "window) declared alongside each query. Conceptual queries carry no rule and need a",
        "human; until they are labelled they are simply absent from the numbers.",
        "",
        "## Results",
        "",
        "| method | " + " | ".join(METRIC_ORDER) + " | queries |",
        "|---|" + "---|" * (len(METRIC_ORDER) + 1),
    ]
    for method, metrics in results.items():
        row = " | ".join(_fmt(float(metrics.get(m, 0.0))) for m in METRIC_ORDER)
        lines.append(f"| {method} | {row} | {int(metrics.get('queries', 0))} |")

    lines += [
        "",
        "## By category (NDCG@10)",
        "",
        "A category with no judged queries shows `--`; it is not a score of zero.",
        "",
        "| category | judged | " + " | ".join(results.keys()) + " |",
        "|---|---|" + "---|" * len(results),
    ]
    categories = sorted({c for per_method in per_category.values() for c in per_method})
    for category in categories:
        judged_n = 0
        cells = []
        for method in results:
            metrics = per_category.get(method, {}).get(category, {})
            n = int(metrics.get("queries", 0))
            judged_n = max(judged_n, n)
            cells.append(_fmt(float(metrics["ndcg@10"])) if n else "--")
        lines.append(f"| {category} | {judged_n} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## Caveats",
        "",
        "**Recall@50 is inflated by pool bias.** The judged documents are the union of the",
        "top 20 from each method, so by construction every relevant document is one that one",
        "of these systems already found. Hybrid fuses both legs and therefore covers most of",
        "that union, which is why its recall approaches 1.0. Recall here measures how much of",
        "the pool a method recovers, not how much of the corpus it missed. Treat NDCG@10 and",
        "MRR as the meaningful comparison; use recall only between methods, never as an",
        "absolute.",
        "",
        "**The judged subset skews lexical.** Objective rules only exist where relevance is",
        "derivable from the document -- an exact phrase, a sender, a date window. Those are",
        "precisely the queries keyword matching is good at, while the 12 conceptual queries,",
        "where semantic retrieval is supposed to earn its keep, are the ones still awaiting",
        "human labels. The vector leg is therefore being judged mostly on the terrain that",
        "suits it least, and its standing should be expected to improve once the conceptual",
        "queries are labelled.",
    ]
    lines += ["", "## Query set", "", "| id | category | query | judged |", "|---|---|---|---|"]
    judged_ids = set(coverage["judged_ids"])
    for query in queries:
        mark = "yes" if query["id"] in judged_ids else "no"
        text = str(query["query"]).replace("|", "\\|")
        lines.append(f"| {query['id']} | {query['category']} | `{text}` | {mark} |")

    lines.append("")
    return "\n".join(lines)
