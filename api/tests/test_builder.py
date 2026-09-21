"""Unit tests for Elasticsearch request construction (no cluster needed)."""

from __future__ import annotations

from app.search.builder import (
    BM25_FIELDS,
    best_highlight,
    build_bm25_query,
    build_filters,
    build_knn,
    phrase_filters,
)
from app.search.parser import FUZZINESS, parse


def test_address_operator_becomes_an_exact_term() -> None:
    filters = build_filters(parse("from:john.arnold@enron.com"))
    assert filters == [{"term": {"from": "john.arnold@enron.com"}}]


def test_name_operator_becomes_a_text_match() -> None:
    filters = build_filters(parse('from:"John Arnold"'))
    assert filters[0]["match"]["from.text"]["query"] == "john arnold"


def test_multiple_values_on_one_field_become_a_should() -> None:
    filters = build_filters(parse("from:a@enron.com from:b@enron.com"))
    assert filters[0]["bool"]["minimum_should_match"] == 1
    assert len(filters[0]["bool"]["should"]) == 2


def test_date_range_is_inclusive_of_the_end_day() -> None:
    filters = build_filters(parse("after:2001-07-01 before:2001-12-31"))
    rng = filters[0]["range"]["date"]
    assert rng["gte"] == "2001-07-01"
    assert rng["lte"].startswith("2001-12-31T23:59:59")


def test_only_after_produces_an_open_ended_range() -> None:
    rng = build_filters(parse("after:2001-07-01"))[0]["range"]["date"]
    assert "gte" in rng and "lte" not in rng


def test_bm25_applies_length_scaled_fuzziness_and_field_boosts() -> None:
    query = build_bm25_query(parse("raptor partnership"), [])
    mm = query["bool"]["must"][0]["multi_match"]
    assert mm["fields"] == BM25_FIELDS
    assert "subject^3" in mm["fields"]
    assert mm["fuzziness"] == FUZZINESS


def test_phrases_become_phrase_clauses_on_exact_subfields() -> None:
    query = build_bm25_query(parse('"hiding losses"'), [])
    clause = query["bool"]["must"][0]["bool"]["should"]
    fields = {next(iter(c["match_phrase"])) for c in clause}
    assert fields == {"subject.exact", "body.exact"}


def test_filter_only_query_falls_back_to_match_all() -> None:
    parsed = parse("from:a@enron.com")
    filters = build_filters(parsed)
    query = build_bm25_query(parsed, filters)
    assert query["bool"]["must"] == [{"match_all": {}}]
    assert query["bool"]["filter"] == filters


def test_knn_carries_the_same_filters_and_requests_inner_hits() -> None:
    """Flaw #12: the vector leg must not ignore the user's filters."""
    filters = build_filters(parse("from:a@enron.com"))
    knn = build_knn([0.1] * 8, filters, k=10, num_candidates=100)
    assert knn["field"] == "chunks.vector"
    assert knn["filter"]["bool"]["filter"] == filters
    assert knn["inner_hits"]["size"] == 1
    assert knn["k"] == 10 and knn["num_candidates"] == 100


def test_knn_without_filters_omits_the_filter_key() -> None:
    assert "filter" not in build_knn([0.1] * 8, [], k=5, num_candidates=50)


def test_best_highlight_prefers_exact_body_fragments() -> None:
    assert best_highlight({"body": ["b"], "body.exact": ["e"]}) == ["e"]
    assert best_highlight({"subject": ["s"]}) == ["s"]
    assert best_highlight(None) == []
    assert best_highlight({}) == []


def test_subject_operator_becomes_a_subject_match_filter() -> None:
    filters = build_filters(parse("subject:Raptor"))
    assert filters == [{"match": {"subject": {"query": "Raptor", "operator": "and"}}}]


def test_best_highlight_ignores_unknown_fields() -> None:
    assert best_highlight({"some.other.field": ["x"]}) == []


def test_phrase_filters_require_each_phrase_on_the_exact_subfields() -> None:
    filters = phrase_filters(parse('"force majeure" "credit rating" gas'))
    assert len(filters) == 2
    for clause, phrase in zip(filters, ("force majeure", "credit rating"), strict=True):
        should = clause["bool"]["should"]
        assert clause["bool"]["minimum_should_match"] == 1
        assert {next(iter(c["match_phrase"])) for c in should} == {"subject.exact", "body.exact"}
        assert should[1]["match_phrase"]["body.exact"] == phrase


def test_phrase_filters_are_empty_without_phrases() -> None:
    assert phrase_filters(parse("force majeure")) == []
