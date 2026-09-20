"""Kill a node under live load, then show the cluster absorb it and recover.

The sequence (CLAUDE_CODE_KICKOFF.md section 8):
  1. load runs against the API while the cluster is green
  2. ``docker kill`` one node -- an abrupt SIGKILL, not a graceful shutdown
  3. load continues while the cluster is yellow and a replica is promoted
  4. the node is restarted and shards recover
  5. load stops; every request is bucketed by when it was issued

The target is zero failed requests. That only holds because the API's client
holds all three nodes (``ES_HOST`` is a list) and retries elsewhere when one
stops answering -- with a single host configured, this run fails outright.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ops.bench.runner import BenchConfig, Sample, Summary, run_bench, summarise
from ops.chaos.cluster import ClusterWatcher, docker


@dataclass(frozen=True)
class ChaosConfig:
    container: str = "elastic-search-es02-1"
    before_s: float = 20.0
    during_s: float = 40.0
    after_s: float = 60.0
    poll_interval_s: float = 1.0
    index_pattern: str = "emails-*"


@dataclass
class Phase:
    name: str
    started: float
    ended: float = 0.0

    def contains(self, at: float) -> bool:
        return self.started <= at < (self.ended or float("inf"))


@dataclass
class ChaosResult:
    phases: list[Phase] = field(default_factory=list)
    events: list[tuple[float, str]] = field(default_factory=list)
    buckets: dict[str, Summary] = field(default_factory=dict)
    overall: Summary = field(default_factory=Summary)
    transitions: list[tuple[float, str]] = field(default_factory=list)
    shards_before: list[dict[str, str]] = field(default_factory=list)
    shards_during: list[dict[str, str]] = field(default_factory=list)
    shards_after: list[dict[str, str]] = field(default_factory=list)
    t0: float = 0.0


def promoted_replicas(
    before: Sequence[dict[str, str]], during: Sequence[dict[str, str]]
) -> list[str]:
    """Shards whose primary moved onto a node that previously held its replica.

    Comparing shard ids alone is not enough: every shard has both a primary and
    a replica in both snapshots, so an untouched shard would look promoted. The
    evidence of promotion is that the node now serving the primary is one that
    was serving a *replica* before the kill.
    """
    replica_nodes: dict[str, set[str]] = {}
    for row in before:
        if row.get("prirep") == "r" and row.get("node"):
            key = f"{row['index']}/{row['shard']}"
            replica_nodes.setdefault(key, set()).add(row["node"])

    promoted = [
        key
        for row in during
        if row.get("prirep") == "p"
        and row.get("node")
        and (key := f"{row['index']}/{row['shard']}") in replica_nodes
        and row["node"] in replica_nodes[key]
    ]
    return sorted(set(promoted))


async def _watch(watcher: ClusterWatcher, interval: float, stop: asyncio.Event) -> None:
    """Poll cluster health on its own cadence while load runs."""
    while not stop.is_set():
        await asyncio.to_thread(watcher.poll)
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            continue


async def run_chaos(
    bench: BenchConfig, chaos: ChaosConfig, queries: Sequence[str], watcher: ClusterWatcher
) -> ChaosResult:
    result = ChaosResult()
    samples: list[Sample] = []
    stop_load = asyncio.Event()
    stop_watch = asyncio.Event()

    result.t0 = time.monotonic()
    load = asyncio.create_task(run_bench(bench, queries, collector=samples, stop=stop_load))
    watch = asyncio.create_task(_watch(watcher, chaos.poll_interval_s, stop_watch))

    def event(text: str) -> None:
        result.events.append((time.monotonic(), text))

    # --- 1. steady state ---------------------------------------------------
    before = Phase("before", time.monotonic())
    await asyncio.sleep(chaos.before_s)
    result.shards_before = await asyncio.to_thread(watcher.shards, chaos.index_pattern)
    before.ended = time.monotonic()

    # --- 2. kill -----------------------------------------------------------
    await asyncio.to_thread(docker, "kill", chaos.container)
    event(f"docker kill {chaos.container}")
    during = Phase("during", time.monotonic())

    # --- 3. degraded -------------------------------------------------------
    await asyncio.sleep(chaos.during_s)
    result.shards_during = await asyncio.to_thread(watcher.shards, chaos.index_pattern)
    during.ended = time.monotonic()

    # --- 4. restart + recovery --------------------------------------------
    await asyncio.to_thread(docker, "start", chaos.container)
    event(f"docker start {chaos.container}")
    after = Phase("after", time.monotonic())

    deadline = time.monotonic() + chaos.after_s
    while time.monotonic() < deadline:
        await asyncio.sleep(chaos.poll_interval_s)
        if watcher.samples and watcher.samples[-1].status == "green":
            event("cluster returned to green")
            break
    after.ended = time.monotonic()

    # --- 5. stop -----------------------------------------------------------
    stop_load.set()
    stop_watch.set()
    await load
    await watch
    result.shards_after = await asyncio.to_thread(watcher.shards, chaos.index_pattern)

    result.phases = [before, during, after]
    result.buckets = {
        phase.name: summarise([s for s in samples if phase.contains(s.at)])
        for phase in result.phases
    }
    result.overall = summarise(samples)
    result.transitions = watcher.transitions()
    return result


def context_of(result: ChaosResult) -> dict[str, Any]:
    return {
        "promoted_replicas": promoted_replicas(result.shards_before, result.shards_during),
        "transitions": [
            {"t": round(at - result.t0, 1), "status": status} for at, status in result.transitions
        ],
        "events": [{"t": round(at - result.t0, 1), "event": text} for at, text in result.events],
    }
