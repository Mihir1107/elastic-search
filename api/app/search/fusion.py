"""Manual Reciprocal Rank Fusion.

Done in Python rather than with Elasticsearch's ``rrf`` retriever because RRF's
availability on the Basic licence is genuinely ambiguous and the product rule is
that nothing may depend on a paid feature (DECISIONS D1). The API probes the
native retriever at startup and logs what it finds, but never relies on it.

score(d) = sum over legs of 1 / (k + rank_in_leg(d)), k = 60
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

RRF_K = 60


@dataclass
class FusedHit:
    doc_id: str
    score: float
    ranks: dict[str, int] = field(default_factory=dict)
    source: dict[str, Any] = field(default_factory=dict)
    highlight: dict[str, list[str]] = field(default_factory=dict)
    chunk: str | None = None

    @property
    def matched_by(self) -> list[str]:
        return sorted(self.ranks)


def rrf_scores(rankings: Sequence[Sequence[str]], k: int = RRF_K) -> dict[str, float]:
    """Raw RRF scores for one or more ranked id lists."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def fuse(
    legs: dict[str, list[dict[str, Any]]],
    k: int = RRF_K,
) -> list[FusedHit]:
    """Fuse named legs of ES hits into one ranked list.

    ``legs`` maps a leg name ("bm25", "knn") to that leg's hits in rank order.
    Ties break on doc id so the ordering is deterministic.
    """
    rankings = [[hit["_id"] for hit in hits] for hits in legs.values()]
    scores = rrf_scores(rankings, k=k)

    merged: dict[str, FusedHit] = {}
    for leg_name, hits in legs.items():
        for rank, hit in enumerate(hits, start=1):
            doc_id = hit["_id"]
            entry = merged.get(doc_id)
            if entry is None:
                entry = FusedHit(doc_id=doc_id, score=scores[doc_id])
                merged[doc_id] = entry
            entry.ranks[leg_name] = rank
            if hit.get("_source") and not entry.source:
                entry.source = hit["_source"]
            if hit.get("highlight") and not entry.highlight:
                entry.highlight = hit["highlight"]
            chunk = _inner_chunk(hit)
            if chunk and entry.chunk is None:
                entry.chunk = chunk

    return sorted(merged.values(), key=lambda h: (-h.score, h.doc_id))


def _inner_chunk(hit: dict[str, Any]) -> str | None:
    """Best-matching nested chunk text from a kNN hit's inner_hits."""
    inner = hit.get("inner_hits") or {}
    chunk_hits = (inner.get("chunk") or {}).get("hits", {}).get("hits", [])
    if not chunk_hits:
        return None
    source = chunk_hits[0].get("_source") or {}
    text = source.get("text")
    return str(text) if text else None
