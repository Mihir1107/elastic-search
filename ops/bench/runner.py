"""Async load driver + percentile summaries for the search API."""

from __future__ import annotations

import asyncio
import math
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml

#: Stage timings the API reports (app/models.py: Timings). Kept explicit rather
#: than discovered from the payload so a renamed stage fails loudly here.
STAGES = ("parse_ms", "embed_ms", "bm25_ms", "knn_ms", "fuse_ms", "rerank_ms", "total_ms")


@dataclass(frozen=True)
class BenchConfig:
    base_url: str = "http://127.0.0.1:8000"
    concurrency: int = 4
    iterations: int = 5
    warmup: int = 5
    size: int | None = None
    rerank: bool = False
    timeout_s: float = 30.0


@dataclass(frozen=True)
class Sample:
    query: str
    status: int
    wall_ms: float
    timings: dict[str, float]
    hits: int
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.status == 200


@dataclass
class Summary:
    requests: int = 0
    failed: int = 0
    wall: dict[str, float] = field(default_factory=dict)
    stages: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        return 1.0 if self.requests == 0 else (self.requests - self.failed) / self.requests


def load_queries(path: Path) -> list[str]:
    """Query strings from the evaluation set -- real queries, mixed categories."""
    data = yaml.safe_load(path.read_text())
    queries = [str(q["query"]) for q in data.get("queries", []) if q.get("query")]
    if not queries:
        msg = f"no queries in {path}"
        raise ValueError(msg)
    return queries


def percentile(values: Sequence[float], pct: float) -> float:
    """Nearest-rank percentile: the smallest value at or above ``pct`` of the data.

    ``ceil(pct/100 * N)``, so p95 of 100 sorted samples is the 95th, not the 96th.
    Explicit rather than ``statistics.quantiles`` because the chaos run prints the
    same figure over small, unevenly sized buckets where interpolation misleads.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, min(len(ordered), math.ceil(pct / 100.0 * len(ordered))))
    return ordered[rank - 1]


def _distribution(values: Sequence[float]) -> dict[str, float]:
    if not values:
        return {"n": 0, "mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    return {
        "n": len(values),
        "mean": round(statistics.fmean(values), 1),
        "p50": round(percentile(values, 50), 1),
        "p95": round(percentile(values, 95), 1),
        "p99": round(percentile(values, 99), 1),
        "max": round(max(values), 1),
    }


def summarise(samples: Sequence[Sample]) -> Summary:
    ok = [s for s in samples if s.ok]
    summary = Summary(requests=len(samples), failed=len(samples) - len(ok))
    summary.wall = _distribution([s.wall_ms for s in ok])
    for stage in STAGES:
        summary.stages[stage] = _distribution([s.timings.get(stage, 0.0) for s in ok])
    return summary


async def _one(client: httpx.AsyncClient, cfg: BenchConfig, query: str) -> Sample:
    params: dict[str, Any] = {"q": query}
    if cfg.size is not None:
        params["size"] = cfg.size
    if cfg.rerank:
        params["rerank"] = "true"

    started = time.perf_counter()
    try:
        response = await client.get("/search", params=params)
    except (TimeoutError, httpx.HTTPError) as exc:
        wall = (time.perf_counter() - started) * 1000
        return Sample(query, 0, wall, {}, 0, error=type(exc).__name__)

    wall = (time.perf_counter() - started) * 1000
    if response.status_code != 200:
        status = response.status_code
        return Sample(query, status, wall, {}, 0, error=f"http-{status}")

    body = response.json()
    timings = {k: float(v) for k, v in (body.get("timings") or {}).items()}
    return Sample(query, 200, wall, timings, len(body.get("results") or []))


async def run_bench(
    cfg: BenchConfig,
    queries: Sequence[str],
    *,
    collector: list[Sample] | None = None,
    stop: asyncio.Event | None = None,
) -> list[Sample]:
    """Fire ``iterations`` passes over ``queries`` at ``concurrency``.

    ``collector`` receives samples as they land (the chaos run reads it live to
    bucket requests into before / during / after a node kill). ``stop`` ends the
    run early, which is how the chaos run holds load open for a fixed wall time.
    """
    samples: list[Sample] = collector if collector is not None else []
    work: asyncio.Queue[str] = asyncio.Queue()
    for _ in range(cfg.iterations):
        for query in queries:
            work.put_nowait(query)

    limits = httpx.Limits(max_connections=cfg.concurrency * 2)
    async with httpx.AsyncClient(
        base_url=cfg.base_url, timeout=cfg.timeout_s, limits=limits
    ) as client:
        for query in queries[: cfg.warmup]:
            await _one(client, cfg, query)

        async def worker() -> None:
            while not (stop is not None and stop.is_set()):
                try:
                    query = work.get_nowait()
                except asyncio.QueueEmpty:
                    return
                samples.append(await _one(client, cfg, query))

        await asyncio.gather(*(worker() for _ in range(cfg.concurrency)))
    return samples
