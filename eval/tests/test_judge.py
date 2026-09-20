"""Tests for objective grading rules and qrels storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from eval.judge import (
    Judgment,
    auto_grade,
    grade_pool,
    load_judgments,
    load_qrels,
    save_judgments,
)


def _doc(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "d1",
        "subject": "Raptor partnership",
        "body": "We discussed the natural gas position today.",
        "from": "john.arnold@enron.com",
        "to": ["tim.belden@enron.com"],
        "date": "2001-07-15T10:00:00+00:00",
    }
    base.update(kw)
    return base


# ------------------------------- phrase


def test_phrase_rule_requires_the_literal_phrase() -> None:
    rule = {"kind": "phrase", "phrase": "natural gas"}
    assert auto_grade(rule, _doc()) == 3
    assert auto_grade(rule, _doc(body="nothing relevant here")) == 0


def test_phrase_rule_is_case_insensitive_and_searches_the_subject() -> None:
    rule = {"kind": "phrase", "phrase": "raptor partnership"}
    assert auto_grade(rule, _doc(body="")) == 3


# ------------------------------- filter


def test_filter_rule_matches_sender_and_date_window() -> None:
    rule = {
        "kind": "filter",
        "from": "john.arnold@enron.com",
        "after": "2001-06-01",
        "before": "2001-09-30",
    }
    assert auto_grade(rule, _doc()) == 3
    assert auto_grade(rule, _doc(**{"from": "someone.else@enron.com"})) == 0
    assert auto_grade(rule, _doc(date="2001-10-05T10:00:00+00:00")) == 0
    assert auto_grade(rule, _doc(date="2001-05-05T10:00:00+00:00")) == 0


def test_filter_rule_boundaries_are_inclusive() -> None:
    rule = {"kind": "filter", "after": "2001-07-15", "before": "2001-07-15"}
    assert auto_grade(rule, _doc()) == 3


def test_filter_rule_matches_a_recipient() -> None:
    rule = {"kind": "filter", "to": "TIM.BELDEN@enron.com"}
    assert auto_grade(rule, _doc()) == 3
    assert auto_grade(rule, _doc(to=["other@enron.com"])) == 0


def test_filter_rule_rejects_an_unparseable_date() -> None:
    rule = {"kind": "filter", "after": "2001-01-01"}
    assert auto_grade(rule, _doc(date=None)) == 0


# ------------------------------- terms / both


def test_terms_rule_grades_all_versus_some() -> None:
    assert auto_grade({"kind": "terms", "terms": ["gas", "position"]}, _doc()) == 3
    assert auto_grade({"kind": "terms", "terms": ["gas", "absent"]}, _doc()) == 2
    assert auto_grade({"kind": "terms", "terms": ["absent"]}, _doc()) == 0


def test_both_rule_needs_the_filter_and_rewards_the_topic() -> None:
    rule = {"kind": "both", "from": "john.arnold@enron.com", "terms": ["gas"]}
    assert auto_grade(rule, _doc()) == 3
    # right sender, wrong topic -> still partially on target
    assert auto_grade(rule, _doc(body="lunch plans", subject="lunch")) == 1
    # wrong sender -> irrelevant regardless of topic
    assert auto_grade(rule, _doc(**{"from": "x@enron.com"})) == 0


def test_unknown_rule_kind_grades_zero() -> None:
    assert auto_grade({"kind": "nope"}, _doc()) == 0


# ------------------------------- pooling / storage


def test_grade_pool_skips_queries_without_a_rule() -> None:
    assert grade_pool({"id": "q1", "query": "x"}, [_doc()]) == []


def test_grade_pool_tags_the_source_with_the_rule_kind() -> None:
    query = {"id": "q1", "auto": {"kind": "phrase", "phrase": "natural gas"}}
    graded = grade_pool(query, [_doc()])
    assert graded[0].source == "auto:phrase"
    assert graded[0].grade == 3


def test_human_labels_win_over_auto_for_the_same_pair(tmp_path: Path) -> None:
    path = tmp_path / "qrels.jsonl"
    save_judgments(
        path,
        [
            Judgment("q1", "d1", 3, "auto:phrase"),
            Judgment("q1", "d1", 1, "human"),
            Judgment("q1", "d2", 2, "auto:terms"),
        ],
    )
    stored = {(j.query_id, j.doc_id): j for j in load_judgments(path)}
    assert stored[("q1", "d1")].grade == 1
    assert stored[("q1", "d1")].source == "human"
    assert stored[("q1", "d2")].grade == 2


def test_auto_does_not_overwrite_an_existing_human_label(tmp_path: Path) -> None:
    path = tmp_path / "qrels.jsonl"
    save_judgments(path, [Judgment("q1", "d1", 1, "human"), Judgment("q1", "d1", 3, "auto:phrase")])
    assert load_judgments(path)[0].grade == 1


def test_load_qrels_shapes_the_mapping_metrics_expect(tmp_path: Path) -> None:
    path = tmp_path / "qrels.jsonl"
    save_judgments(path, [Judgment("q1", "d1", 3, "human"), Judgment("q1", "d2", 0, "human")])
    assert load_qrels(path) == {"q1": {"d1": 3, "d2": 0}}


def test_missing_qrels_file_is_empty(tmp_path: Path) -> None:
    assert load_qrels(tmp_path / "nope.jsonl") == {}
    assert load_judgments(tmp_path / "nope.jsonl") == []
