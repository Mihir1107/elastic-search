"""Render a benchmark run as markdown + JSON."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ops.bench.runner import STAGES, BenchConfig, Summary

#: The gate from docs/SPEC.md (section 2, criterion 8): p95 under 300ms
#: excluding rerank.
P95_TARGET_MS = 300.0


def _table(rows: list[tuple[str, dict[str, float]]]) -> str:
    head = "| stage | n | mean | p50 | p95 | p99 | max |\n|---|---:|---:|---:|---:|---:|---:|"
    body = "\n".join(
        f"| {name} | {d['n']:.0f} | {d['mean']:.1f} | {d['p50']:.1f} | "
        f"{d['p95']:.1f} | {d['p99']:.1f} | {d['max']:.1f} |"
        for name, d in rows
    )
    return f"{head}\n{body}"


def to_dict(cfg: BenchConfig, summary: Summary, *, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "written_at": datetime.now(UTC).isoformat(),
        "config": asdict(cfg),
        "context": context,
        "requests": summary.requests,
        "failed": summary.failed,
        "success_rate": summary.success_rate,
        "wall_ms": summary.wall,
        "stages_ms": summary.stages,
        "p95_target_ms": P95_TARGET_MS,
        "p95_target_met": summary.wall.get("p95", 0.0) < P95_TARGET_MS,
    }


def to_markdown(cfg: BenchConfig, summary: Summary, *, context: dict[str, Any]) -> str:
    wall_p95 = summary.wall.get("p95", 0.0)
    verdict = "**MET**" if wall_p95 < P95_TARGET_MS else "**NOT MET**"
    lines = [
        "# Search latency benchmark",
        "",
        f"Run at {datetime.now(UTC).isoformat(timespec='seconds')}.",
        "",
        "| setting | value |",
        "|---|---|",
        f"| index | `{context.get('index', '?')}` |",
        f"| documents | {context.get('docs', '?')} |",
        f"| concurrency | {cfg.concurrency} |",
        f"| iterations | {cfg.iterations} |",
        f"| rerank | {cfg.rerank} |",
        f"| requests | {summary.requests} ({summary.failed} failed) |",
        "",
        "## Client wall time (the number the gate is about)",
        "",
        _table([("wall", summary.wall)]),
        "",
        f"p95 = {wall_p95:.1f} ms against a {P95_TARGET_MS:.0f} ms target: {verdict}",
        "",
        "## Server stage breakdown",
        "",
        "Self-reported by the API, so these exclude transport and serialisation;",
        "the gap between `total_ms` and client wall time is exactly that overhead.",
        "",
        _table([(stage, summary.stages[stage]) for stage in STAGES]),
        "",
    ]
    return "\n".join(lines)


def write(
    cfg: BenchConfig, summary: Summary, out_dir: Path, *, context: dict[str, Any], label: str
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{label}.json"
    md_path = out_dir / f"{label}.md"
    json_path.write_text(json.dumps(to_dict(cfg, summary, context=context), indent=2) + "\n")
    md_path.write_text(to_markdown(cfg, summary, context=context))
    return json_path, md_path
