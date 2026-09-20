"""Unit tests for service helpers that need no cluster."""

from __future__ import annotations

from app.search.facets import build_aggs, parse_aggs
from app.search.fusion import FusedHit
from app.search.parser import parse
from app.search.service import (
    _snippets,
    _to_hit,
    _understood,
    decode_page_token,
    encode_page_token,
)


def test_page_token_round_trip() -> None:
    assert decode_page_token(encode_page_token(40)) == 40


def test_missing_or_corrupt_token_is_offset_zero() -> None:
    for token in (None, "", "!!!", "Zm9v", "////"):
        assert decode_page_token(token) == 0


def test_negative_offsets_are_clamped() -> None:
    assert decode_page_token(encode_page_token(-5)) == 0


def test_understood_echoes_the_parse_with_from_alias() -> None:
    understood = _understood(parse('from:a@enron.com "x y" after:2001-01-01 raptor'))
    payload = understood.model_dump(by_alias=True)
    assert payload["from"] == ["a@enron.com"]
    assert payload["phrases"] == ["x y"]
    assert payload["terms"] == ["raptor"]
    assert payload["after"] == "2001-01-01"


def test_snippet_prefers_highlight_then_chunk_then_body() -> None:
    assert _snippets(FusedHit("a", 1.0, highlight={"body": ["hl"]})) == ["hl"]
    assert _snippets(FusedHit("a", 1.0, chunk="chunk text")) == ["chunk text"]
    assert _snippets(FusedHit("a", 1.0, source={"body": "plain body"})) == ["plain body"]
    assert _snippets(FusedHit("a", 1.0)) == []


def test_long_body_snippet_is_truncated_with_an_ellipsis() -> None:
    hit = FusedHit("a", 1.0, source={"body": "x" * 500})
    assert _snippets(hit)[0].endswith("...")


def test_to_hit_maps_source_fields_and_alias() -> None:
    hit = _to_hit(
        FusedHit(
            "id1",
            0.5,
            ranks={"bm25": 1},
            source={
                "subject": "Raptor",
                "from": "a@enron.com",
                "to": ["b@enron.com"],
                "date": "2001-05-14T23:39:00+00:00",
                "duplicate_count": 3,
            },
        )
    )
    payload = hit.model_dump(by_alias=True)
    assert payload["from"] == "a@enron.com"
    assert payload["subject"] == "Raptor"
    assert payload["duplicate_count"] == 3
    assert payload["matched_by"] == ["bm25"]


def test_aggregations_cover_the_required_facets() -> None:
    aggs = build_aggs()
    assert {"top_senders", "top_recipients", "over_time", "folders"} <= set(aggs)
    assert aggs["over_time"]["date_histogram"]["calendar_interval"] == "month"


def test_parse_aggs_flattens_buckets() -> None:
    response = {
        "aggregations": {
            "top_senders": {"buckets": [{"key": "a@enron.com", "doc_count": 3}]},
            "over_time": {"buckets": [{"key_as_string": "2001-05", "key": 1, "doc_count": 2}]},
        }
    }
    facets = parse_aggs(response)
    assert facets["top_senders"] == [{"key": "a@enron.com", "count": 3}]
    assert facets["over_time"][0]["key"] == "2001-05"


def test_parse_aggs_handles_a_response_without_aggregations() -> None:
    assert parse_aggs({}) == {}
