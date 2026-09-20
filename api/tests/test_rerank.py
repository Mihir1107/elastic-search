"""Unit tests for the local cross-encoder reranker (no model is loaded)."""

from __future__ import annotations

from typing import Any

import pytest

from app.search import rerank as rerank_mod
from app.search.fusion import FusedHit


class _FakeCrossEncoder:
    """Scores by position in a lookup, so ordering is deterministic in tests."""

    def __init__(self, scores: dict[str, float]) -> None:
        self.scores = scores
        self.seen: list[tuple[str, str]] = []

    def predict(self, pairs: list[tuple[str, str]], **_: Any) -> list[float]:
        self.seen = pairs
        return [self.scores.get(doc.split("\n")[0], 0.0) for _, doc in pairs]


@pytest.fixture(autouse=True)
def _reset() -> Any:
    rerank_mod.reset_cache()
    yield
    rerank_mod.reset_cache()


def _hit(doc_id: str, subject: str, score: float, **kw: Any) -> FusedHit:
    return FusedHit(doc_id=doc_id, score=score, source={"subject": subject, **kw})


def test_document_text_prefers_the_matching_chunk_over_the_body() -> None:
    hit = FusedHit("a", 1.0, source={"subject": "S", "body": "long body"}, chunk="chunk text")
    assert rerank_mod.document_text(hit) == "S\nchunk text"


def test_document_text_falls_back_to_the_body() -> None:
    hit = FusedHit("a", 1.0, source={"subject": "S", "body": "the body"})
    assert rerank_mod.document_text(hit) == "S\nthe body"


def test_document_text_is_truncated() -> None:
    hit = FusedHit("a", 1.0, source={"subject": "S", "body": "x" * 5000})
    assert len(rerank_mod.document_text(hit)) <= rerank_mod.MAX_DOC_CHARS + len("S\n")


def test_rerank_reorders_by_cross_encoder_score(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCrossEncoder({"low": 0.1, "high": 0.9, "mid": 0.5})
    monkeypatch.setattr(rerank_mod, "get_reranker", lambda name: fake)

    hits = [_hit("1", "low", 9.0), _hit("2", "mid", 8.0), _hit("3", "high", 7.0)]
    out = rerank_mod.rerank("query", hits, "model", window=10)

    assert [h.source["subject"] for h in out] == ["high", "mid", "low"]
    assert out[0].score == pytest.approx(0.9)


def test_rerank_only_touches_the_window_and_keeps_the_tail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCrossEncoder({"a": 0.1, "b": 0.9})
    monkeypatch.setattr(rerank_mod, "get_reranker", lambda name: fake)

    hits = [_hit("1", "a", 5.0), _hit("2", "b", 4.0), _hit("3", "tail", 3.0)]
    out = rerank_mod.rerank("query", hits, "model", window=2)

    assert [h.doc_id for h in out] == ["2", "1", "3"], "tail must keep its place"
    assert len(fake.seen) == 2, "only the window is scored"
    assert out[2].score == 3.0, "tail scores are untouched"


def test_rerank_passes_the_query_with_each_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeCrossEncoder({"a": 1.0})
    monkeypatch.setattr(rerank_mod, "get_reranker", lambda name: fake)
    rerank_mod.rerank("find losses", [_hit("1", "a", 1.0)], "model", window=5)
    assert fake.seen[0][0] == "find losses"


def test_rerank_is_a_noop_without_hits_or_query(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"n": 0}

    def _boom(name: str) -> Any:
        called["n"] += 1
        raise AssertionError("model must not load")

    monkeypatch.setattr(rerank_mod, "get_reranker", _boom)
    assert rerank_mod.rerank("q", [], "model", window=5) == []
    hits = [_hit("1", "a", 1.0)]
    assert rerank_mod.rerank("   ", hits, "model", window=5) == hits
    assert called["n"] == 0


def test_ties_break_deterministically(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeCrossEncoder({"a": 0.5, "b": 0.5})
    monkeypatch.setattr(rerank_mod, "get_reranker", lambda name: fake)
    hits = [_hit("z", "a", 1.0), _hit("y", "b", 2.0)]
    first = [h.doc_id for h in rerank_mod.rerank("q", hits, "m", window=5)]
    hits2 = [_hit("z", "a", 1.0), _hit("y", "b", 2.0)]
    second = [h.doc_id for h in rerank_mod.rerank("q", hits2, "m", window=5)]
    assert first == second == ["y", "z"]
