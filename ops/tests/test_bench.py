"""Unit tests for the benchmark's maths and sample handling (no API needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ops.bench.runner import Sample, load_queries, percentile, summarise


def test_percentile_is_nearest_rank() -> None:
    values = [float(i) for i in range(1, 101)]
    assert percentile(values, 50) == 50.0
    assert percentile(values, 95) == 95.0
    assert percentile(values, 99) == 99.0
    assert percentile(values, 100) == 100.0


def test_percentile_handles_degenerate_inputs() -> None:
    assert percentile([], 95) == 0.0
    assert percentile([7.0], 95) == 7.0


def _sample(wall: float, *, ok: bool = True) -> Sample:
    if not ok:
        return Sample("q", 503, wall, {}, 0, error="http-503")
    return Sample("q", 200, wall, {"bm25_ms": wall / 2, "total_ms": wall}, 10)


def test_summarise_excludes_failures_from_latency() -> None:
    """A failed request has no meaningful latency; counting it would flatter p95."""
    samples = [_sample(float(i)) for i in range(1, 101)] + [_sample(9999.0, ok=False)]
    summary = summarise(samples)

    assert summary.requests == 101
    assert summary.failed == 1
    assert summary.wall["n"] == 100
    assert summary.wall["max"] == 100.0
    assert summary.success_rate == pytest.approx(100 / 101)


def test_summarise_reports_every_stage_even_when_unused() -> None:
    summary = summarise([_sample(10.0)])
    assert summary.stages["rerank_ms"]["p95"] == 0.0
    assert summary.stages["bm25_ms"]["p50"] == 5.0


def test_load_queries_reads_the_evaluation_set() -> None:
    queries = load_queries(Path("eval/queries.yaml"))
    assert len(queries) >= 40
    assert all(isinstance(q, str) and q for q in queries)


def test_load_queries_rejects_an_empty_set(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("version: 1\nqueries: []\n")
    with pytest.raises(ValueError, match="no queries"):
        load_queries(path)
