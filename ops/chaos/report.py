"""Render a chaos run: timeline, per-phase latency, and the success rate."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ops.bench.runner import BenchConfig
from ops.chaos.runner import ChaosConfig, ChaosResult, promoted_replicas


def to_dict(bench: BenchConfig, chaos: ChaosConfig, result: ChaosResult) -> dict[str, Any]:
    return {
        "written_at": datetime.now(UTC).isoformat(),
        "bench": asdict(bench),
        "chaos": asdict(chaos),
        "requests": result.overall.requests,
        "failed": result.overall.failed,
        "success_rate": result.overall.success_rate,
        "gate_met": result.overall.failed == 0,
        "phases": {
            name: {
                "requests": summary.requests,
                "failed": summary.failed,
                "wall_ms": summary.wall,
            }
            for name, summary in result.buckets.items()
        },
        "transitions": [
            {"t": round(at - result.t0, 1), "status": status} for at, status in result.transitions
        ],
        "events": [{"t": round(at - result.t0, 1), "event": text} for at, text in result.events],
        "promoted_replicas": promoted_replicas(result.shards_before, result.shards_during),
        "shards": {
            "before": result.shards_before,
            "during": result.shards_during,
            "after": result.shards_after,
        },
    }


def _shard_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "_(no shards reported)_"
    head = "| index | shard | role | state | node |\n|---|---:|---|---|---|"
    ordered = sorted(rows, key=lambda r: (r.get("index", ""), r.get("shard", "")))
    body = "\n".join(
        f"| {r.get('index', '?')} | {r.get('shard', '?')} | "
        f"{'primary' if r.get('prirep') == 'p' else 'replica'} | "
        f"{r.get('state', '?')} | {r.get('node') or '—'} |"
        for r in ordered
    )
    return f"{head}\n{body}"


def to_markdown(bench: BenchConfig, chaos: ChaosConfig, result: ChaosResult) -> str:
    overall = result.overall
    verdict = (
        "**MET** — 0 failed requests"
        if overall.failed == 0
        else (f"**NOT MET** — {overall.failed} failed requests")
    )
    promoted = promoted_replicas(result.shards_before, result.shards_during)

    phase_rows = "\n".join(
        f"| {name} | {s.requests} | {s.failed} | {s.wall.get('p50', 0):.1f} | "
        f"{s.wall.get('p95', 0):.1f} | {s.wall.get('p99', 0):.1f} |"
        for name, s in result.buckets.items()
    )
    timeline = "\n".join(
        f"| {round(at - result.t0, 1)}s | {text} |"
        for at, text in sorted(result.events + result.transitions, key=lambda e: e[0])
    )

    return "\n".join(
        [
            "# Chaos run — single node killed under live load",
            "",
            f"Run at {datetime.now(UTC).isoformat(timespec='seconds')}. "
            f"Killed `{chaos.container}` with `docker kill` (SIGKILL, not a graceful stop).",
            "",
            f"## Gate: {verdict}",
            "",
            f"{overall.requests} requests at concurrency {bench.concurrency}, "
            f"{overall.success_rate * 100:.2f}% successful.",
            "",
            "## Latency by phase",
            "",
            "| phase | requests | failed | p50 ms | p95 ms | p99 ms |",
            "|---|---:|---:|---:|---:|---:|",
            phase_rows,
            "",
            "## Timeline",
            "",
            "| t | event |",
            "|---:|---|",
            timeline,
            "",
            "## Replica promotion",
            "",
            (
                "Shards that were replicas before the kill and primaries during it: "
                + (", ".join(f"`{s}`" for s in promoted) if promoted else "_none_")
            ),
            "",
            "### Before the kill",
            "",
            _shard_table(result.shards_before),
            "",
            "### While the node was down",
            "",
            _shard_table(result.shards_during),
            "",
            "### After recovery",
            "",
            _shard_table(result.shards_after),
            "",
        ]
    )


def write(
    bench: BenchConfig, chaos: ChaosConfig, result: ChaosResult, out_dir: Path, label: str
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{label}.json"
    md_path = out_dir / f"{label}.md"
    json_path.write_text(json.dumps(to_dict(bench, chaos, result), indent=2) + "\n")
    md_path.write_text(to_markdown(bench, chaos, result))
    return json_path, md_path
