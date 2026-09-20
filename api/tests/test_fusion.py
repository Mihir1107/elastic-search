"""Unit tests for manual Reciprocal Rank Fusion."""

from __future__ import annotations

from typing import Any

from app.search.fusion import RRF_K, fuse, rrf_scores


def _hit(doc_id: str, **kw: Any) -> dict[str, Any]:
    hit: dict[str, Any] = {"_id": doc_id, "_source": {"subject": doc_id}}
    hit.update(kw)
    return hit


def test_rrf_score_formula() -> None:
    scores = rrf_scores([["a", "b"]], k=60)
    assert scores["a"] == 1 / 61
    assert scores["b"] == 1 / 62


def test_documents_in_both_legs_outrank_single_leg_documents() -> None:
    scores = rrf_scores([["a", "b"], ["b", "c"]])
    assert scores["b"] > scores["a"] > scores["c"]


def test_default_k_is_sixty() -> None:
    assert RRF_K == 60


def test_fuse_merges_sources_highlights_and_leg_membership() -> None:
    bm25 = [_hit("a", highlight={"body": ["frag"]}), _hit("b")]
    knn = [
        _hit(
            "b",
            inner_hits={"chunk": {"hits": {"hits": [{"_source": {"text": "chunk b"}}]}}},
        ),
        _hit("c"),
    ]
    fused = fuse({"bm25": bm25, "knn": knn})

    by_id = {h.doc_id: h for h in fused}
    assert by_id["b"].matched_by == ["bm25", "knn"]
    assert by_id["a"].matched_by == ["bm25"]
    assert by_id["c"].matched_by == ["knn"]
    assert by_id["a"].highlight == {"body": ["frag"]}
    assert by_id["b"].chunk == "chunk b"
    # b appears in both legs, so it must rank first
    assert fused[0].doc_id == "b"


def test_fusion_is_deterministic_on_ties() -> None:
    legs = {"bm25": [_hit("z"), _hit("a")]}
    first = [h.doc_id for h in fuse(legs)]
    second = [h.doc_id for h in fuse(legs)]
    assert first == second


def test_single_leg_preserves_its_order() -> None:
    fused = fuse({"bm25": [_hit("a"), _hit("b"), _hit("c")]})
    assert [h.doc_id for h in fused] == ["a", "b", "c"]


def test_empty_legs_produce_no_hits() -> None:
    assert fuse({"bm25": [], "knn": []}) == []


def test_missing_inner_hits_yields_no_chunk() -> None:
    fused = fuse({"knn": [_hit("a"), _hit("b", inner_hits={})]})
    assert all(h.chunk is None for h in fused)
