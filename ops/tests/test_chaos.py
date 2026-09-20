"""Unit tests for the chaos run's bucketing and promotion detection."""

from __future__ import annotations

import pytest

from ops.bench.runner import Sample, summarise
from ops.chaos.cluster import ClusterWatcher, HealthSample, busiest_primary_node
from ops.chaos.runner import Phase, promoted_replicas


def test_phase_contains_is_half_open() -> None:
    """Half-open so a request issued exactly at the kill lands in one bucket only."""
    before = Phase("before", started=0.0, ended=10.0)
    during = Phase("during", started=10.0, ended=20.0)

    assert before.contains(0.0)
    assert before.contains(9.999)
    assert not before.contains(10.0)
    assert during.contains(10.0)


def test_phase_without_an_end_is_open_ended() -> None:
    assert Phase("after", started=5.0).contains(1e9)


def test_promoted_replicas_finds_the_shards_that_took_over() -> None:
    before = [
        {"index": "emails-v2", "shard": "0", "prirep": "p", "node": "es01"},
        {"index": "emails-v2", "shard": "0", "prirep": "r", "node": "es02"},
        {"index": "emails-v2", "shard": "1", "prirep": "p", "node": "es02"},
        {"index": "emails-v2", "shard": "1", "prirep": "r", "node": "es03"},
    ]
    # es02 died: shard 1's replica on es03 is now the primary. Shard 0's primary
    # was already on a surviving node, so it was never promoted.
    during = [
        {"index": "emails-v2", "shard": "0", "prirep": "p", "node": "es01"},
        {"index": "emails-v2", "shard": "0", "prirep": "r", "node": ""},  # unassigned
        {"index": "emails-v2", "shard": "1", "prirep": "p", "node": "es03"},
    ]
    assert promoted_replicas(before, during) == ["emails-v2/1"]


def test_promoted_replicas_is_empty_when_nothing_moved() -> None:
    rows = [{"index": "emails-v2", "shard": "0", "prirep": "p", "node": "es01"}]
    assert promoted_replicas(rows, rows) == []


def test_transitions_collapse_repeated_statuses() -> None:
    watcher = ClusterWatcher(hosts=[], username="u", password="p", ca_cert="ca")
    for at, status in [(0, "green"), (1, "green"), (2, "yellow"), (3, "yellow"), (4, "green")]:
        watcher.samples.append(HealthSample(float(at), status, 3, 14, 0, 0, 0))

    assert [s for _, s in watcher.transitions()] == ["green", "yellow", "green"]


def test_bucketing_assigns_each_sample_to_one_phase() -> None:
    phases = [Phase("before", 0.0, 10.0), Phase("during", 10.0, 20.0), Phase("after", 20.0)]
    samples = [Sample("q", 200, 5.0, {}, 1, at=float(t)) for t in range(0, 30)]

    counts = {p.name: summarise([s for s in samples if p.contains(s.at)]).requests for p in phases}
    assert counts == {"before": 10, "during": 10, "after": 10}
    assert sum(counts.values()) == len(samples)


def test_busiest_primary_node_ignores_replicas_and_unassigned() -> None:
    """Killing a replica-only node demonstrates no promotion, so it is not the target."""
    rows = [
        {"index": "e", "shard": "0", "prirep": "p", "node": "es01"},
        {"index": "e", "shard": "1", "prirep": "p", "node": "es01"},
        {"index": "e", "shard": "2", "prirep": "p", "node": "es03"},
        {"index": "e", "shard": "0", "prirep": "r", "node": "es02"},
        {"index": "e", "shard": "1", "prirep": "r", "node": "es02"},
        {"index": "e", "shard": "2", "prirep": "r", "node": ""},
    ]
    assert busiest_primary_node(rows) == "es01"


def test_busiest_primary_node_is_deterministic_on_a_tie() -> None:
    rows = [
        {"index": "e", "shard": "0", "prirep": "p", "node": "es03"},
        {"index": "e", "shard": "1", "prirep": "p", "node": "es01"},
    ]
    assert busiest_primary_node(rows) == "es01"


def test_busiest_primary_node_raises_when_nothing_is_allocated() -> None:
    with pytest.raises(RuntimeError, match="no started primaries"):
        busiest_primary_node([{"index": "e", "shard": "0", "prirep": "r", "node": "es02"}])
