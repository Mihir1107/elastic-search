"""Metric tests with hand-computed expectations."""

from __future__ import annotations

from math import isclose, log2

from eval.metrics import (
    dcg,
    evaluate_run,
    ndcg_at_k,
    recall_at_k,
    reciprocal_rank,
)


def test_dcg_discounts_by_log2_of_rank_plus_one() -> None:
    # rank 1 is undiscounted (log2(2) == 1), rank 2 divides by log2(3)
    assert isclose(dcg([3.0]), 3.0)
    assert isclose(dcg([0.0, 3.0]), 3.0 / log2(3))


def test_ndcg_is_one_for_a_perfect_ranking() -> None:
    qrels = {"a": 3, "b": 0, "c": 1}
    assert isclose(ndcg_at_k(["a", "c", "b"], qrels), 1.0)


def test_ndcg_matches_a_hand_computed_value() -> None:
    qrels = {"a": 3, "b": 0, "c": 1}
    # gains [7, 0, 1] -> DCG 7 + 0 + 1/2 = 7.5 ; ideal [7, 1, 0] -> 7 + 1/log2(3)
    expected = 7.5 / (7 + 1 / log2(3))
    assert isclose(ndcg_at_k(["a", "b", "c"], qrels), expected, rel_tol=1e-9)


def test_ndcg_uses_exponential_gain_so_grade_3_dominates_grade_1() -> None:
    qrels = {"high": 3, "low": 1}
    top_high = ndcg_at_k(["high", "low"], qrels)
    top_low = ndcg_at_k(["low", "high"], qrels)
    assert top_high == 1.0
    assert top_low < 0.75, "a grade-3 doc buried under a grade-1 must cost a lot"


def test_ndcg_truncates_at_k() -> None:
    qrels = {"a": 3}
    assert ndcg_at_k(["x", "y", "a"], qrels, k=2) == 0.0
    assert ndcg_at_k(["x", "y", "a"], qrels, k=3) > 0.0


def test_ndcg_without_judgments_is_zero() -> None:
    assert ndcg_at_k(["a"], {}) == 0.0


def test_ndcg_when_all_grades_are_zero_is_zero() -> None:
    assert ndcg_at_k(["a"], {"a": 0}) == 0.0


def test_reciprocal_rank_finds_the_first_relevant() -> None:
    assert reciprocal_rank(["x", "a"], {"a": 2}) == 0.5
    assert reciprocal_rank(["a", "x"], {"a": 1}) == 1.0
    assert reciprocal_rank(["x", "y"], {"a": 3}) == 0.0


def test_reciprocal_rank_ignores_grade_zero() -> None:
    assert reciprocal_rank(["z", "a"], {"z": 0, "a": 1}) == 0.5


def test_recall_counts_known_relevant_in_the_window() -> None:
    qrels = {"a": 1, "b": 2, "c": 3, "d": 0}
    assert recall_at_k(["a", "b"], qrels, k=50) == 2 / 3
    assert recall_at_k(["a", "b", "c"], qrels, k=50) == 1.0


def test_recall_respects_k() -> None:
    qrels = {"a": 1, "b": 1}
    assert recall_at_k(["x", "a", "b"], qrels, k=2) == 0.5


def test_recall_without_relevant_documents_is_zero() -> None:
    assert recall_at_k(["a"], {"a": 0}) == 0.0


def test_evaluate_run_averages_only_over_judged_queries() -> None:
    runs = {"q1": ["a", "b"], "q2": ["x"], "q3": ["nothing"]}
    qrels = {"q1": {"a": 3}, "q2": {"x": 3}, "q3": {}}
    result = evaluate_run(runs, qrels)
    # q3 has no judgments and must not drag the mean down
    assert result["queries"] == 2
    assert isclose(result["ndcg@10"], 1.0)
    assert isclose(result["mrr"], 1.0)


def test_evaluate_run_with_no_judgments_at_all() -> None:
    result = evaluate_run({"q1": ["a"]}, {})
    assert result["queries"] == 0
    assert result["ndcg@10"] == 0.0
