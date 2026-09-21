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
    per_split: Mapping[str, Mapping[str, Mapping[str, float]]] | None = None,
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
        f" human-labelled: {coverage['human_queries']},"
        f" LLM-labelled: {coverage.get('llm_queries', 0)})",
        f"- Unjudged queries: **{coverage['unjudged_queries']}**"
        " — excluded from the means below, never scored as zero",
        f"- Judgments: {coverage['judgments']}"
        f" ({coverage['auto_judgments']} auto, {coverage['human_judgments']} human,"
        f" {coverage.get('llm_judgments', 0)} LLM)",
        "",
        "Auto-graded judgments come from objective rules (a required phrase, sender or date",
        "window) declared alongside each query. Conceptual queries carry no rule. Their",
        "labels are LLM judgments on the 0-3 rubric in `eval/prelabel.py`, recorded with",
        'source `"llm"`: provisional until a human reviews them (`make eval-label` offers',
        "each one with the LLM grade as the default, and a human answer replaces it).",
        "",
        "## Results",
        "",
        "| method | " + " | ".join(METRIC_ORDER) + " | queries |",
        "|---|" + "---|" * (len(METRIC_ORDER) + 1),
    ]
    for method, metrics in results.items():
        row = " | ".join(_fmt(float(metrics.get(m, 0.0))) for m in METRIC_ORDER)
        lines.append(f"| {method} | {row} | {int(metrics.get('queries', 0))} |")

    if per_split:
        lines += [
            "",
            "## Tune / test split (NDCG@10)",
            "",
            "Queries alternate between `tune` and `test` within each category. Settings are",
            "chosen on `tune`; `test` is the number to believe, because nothing was fitted",
            "to it.",
            "",
            "| method | tune | test |",
            "|---|---|---|",
        ]
        for method, splits in per_split.items():
            cells = [
                _fmt(float(splits[s]["ndcg@10"])) if splits.get(s, {}).get("queries") else "--"
                for s in ("tune", "test")
            ]
            lines.append(f"| {method} | " + " | ".join(cells) + " |")

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
        "**Conceptual NDCG is low in absolute terms, by construction.** Their pools are deep",
        "(the top 10 of every variant compared in D35, 30-45 documents per query), so the",
        "ideal ranking holds far more relevant documents than fit in a top 10. Compare methods",
        "against each other, not against 1.0.",
        "",
        "**Conceptual labels are one LLM's judgment.** Consistent, but not a human's; a",
        "method that shares the labeller's biases could be flattered. The rule-graded",
        "categories carry no such risk and tell the same story.",
    ]
    lines += ["", "## Query set", "", "| id | category | query | judged |", "|---|---|---|---|"]
    judged_ids = set(coverage["judged_ids"])
    for query in queries:
        mark = "yes" if query["id"] in judged_ids else "no"
        text = str(query["query"]).replace("|", "\\|")
        lines.append(f"| {query['id']} | {query['category']} | `{text}` | {mark} |")

    lines.append("")
    return "\n".join(lines)
