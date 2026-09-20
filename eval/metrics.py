"""Ranking metrics: NDCG@10, MRR, Recall@50.

Judgments are graded 0-3 (0 = irrelevant, 3 = exactly what was wanted), so NDCG
uses the standard exponential gain 2^rel - 1. Everything here is pure: it takes
a ranked list of document ids plus a {doc_id: grade} map and returns numbers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import log2

#: A document counts as relevant for MRR/Recall at this grade or above.
RELEVANT_AT = 1


def dcg(gains: Sequence[float]) -> float:
    """Discounted cumulative gain, rank 1 discounted by log2(2)."""
    return sum(gain / log2(rank + 1) for rank, gain in enumerate(gains, start=1))


def ndcg_at_k(ranked: Sequence[str], qrels: Mapping[str, int], k: int = 10) -> float:
    """Normalised DCG over the top k, with exponential gain."""
    if not qrels:
        return 0.0
    gains = [(2 ** qrels.get(doc_id, 0)) - 1 for doc_id in ranked[:k]]
    ideal_grades = sorted(qrels.values(), reverse=True)[:k]
    ideal = [(2**grade) - 1 for grade in ideal_grades]
    best = dcg(ideal)
    if best == 0:
        return 0.0
    return dcg(gains) / best


def reciprocal_rank(ranked: Sequence[str], qrels: Mapping[str, int]) -> float:
    """1 / rank of the first relevant document, else 0."""
    for rank, doc_id in enumerate(ranked, start=1):
        if qrels.get(doc_id, 0) >= RELEVANT_AT:
            return 1.0 / rank
    return 0.0


def recall_at_k(ranked: Sequence[str], qrels: Mapping[str, int], k: int = 50) -> float:
    """Fraction of all known relevant documents that appear in the top k."""
    relevant = {doc for doc, grade in qrels.items() if grade >= RELEVANT_AT}
    if not relevant:
        return 0.0
    found = sum(1 for doc_id in ranked[:k] if doc_id in relevant)
    return found / len(relevant)


def evaluate_run(
    runs: Mapping[str, Sequence[str]],
    qrels: Mapping[str, Mapping[str, int]],
    *,
    ndcg_k: int = 10,
    recall_k: int = 50,
) -> dict[str, float]:
    """Mean metrics over every query that has judgments.

    ``runs`` maps query id -> ranked doc ids. Queries with no judgments are
    skipped rather than scored as zero, which would silently punish a method for
    a gap in the labelling.
    """
    judged = [qid for qid in runs if qrels.get(qid)]
    if not judged:
        return {"ndcg@10": 0.0, "mrr": 0.0, "recall@50": 0.0, "queries": 0}

    ndcgs, rrs, recalls = [], [], []
    for qid in judged:
        ranked = runs[qid]
        rel = qrels[qid]
        ndcgs.append(ndcg_at_k(ranked, rel, ndcg_k))
        rrs.append(reciprocal_rank(ranked, rel))
        recalls.append(recall_at_k(ranked, rel, recall_k))

    n = len(judged)
    return {
        f"ndcg@{ndcg_k}": sum(ndcgs) / n,
        "mrr": sum(rrs) / n,
        f"recall@{recall_k}": sum(recalls) / n,
        "queries": n,
    }
