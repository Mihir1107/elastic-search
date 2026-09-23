"""Unit tests for spelling correction of the embedded text (no cluster needed)."""

from __future__ import annotations

from typing import Any

from app.search.parser import parse
from app.search.spelling import (
    SUGGEST_NAME,
    Correction,
    build_suggest,
    corrected_text,
    corrections,
)


def _entry(text: str, offset: int, suggestion: str | None = None) -> dict[str, Any]:
    options = [{"text": suggestion, "score": 0.9, "freq": 100}] if suggestion else []
    return {"text": text, "offset": offset, "length": len(text), "options": options}


def _response(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"suggest": {SUGGEST_NAME: list(entries)}}


def test_suggest_targets_the_unstemmed_field_and_only_missing_single_edit_words() -> None:
    term = build_suggest(parse("califronia energy"))[SUGGEST_NAME]["term"]  # type: ignore[index]
    assert term["field"] == "body.exact"
    assert term["suggest_mode"] == "missing"
    assert term["max_edits"] == 1


def test_no_suggest_without_free_text() -> None:
    assert build_suggest(parse('"force majeure" from:a@enron.com')) is None


def test_corrections_read_the_top_option_and_skip_tokens_without_one() -> None:
    parsed = parse("califronia energy crisis")
    response = _response(
        _entry("califronia", 0, "california"), _entry("energy", 11), _entry("crisis", 18)
    )
    assert corrections(parsed, response) == [Correction("califronia", "california", 0, 10)]


def test_a_word_the_embedder_knows_is_never_corrected() -> None:
    parsed = parse("software keeps crashing")
    response = _response(_entry("crashing", 15, "crushing"))
    assert corrections(parsed, response, is_known_word=lambda w: w == "crashing") == []


def test_suggestions_whose_offsets_do_not_line_up_are_dropped() -> None:
    parsed = parse("califronia energy")
    response = _response(_entry("califronia", 3, "california"))
    assert corrections(parsed, response) == []


def test_offsets_match_case_insensitively_and_keep_the_users_casing_out() -> None:
    parsed = parse("Califronia energy")
    fixes = corrections(parsed, _response(_entry("califronia", 0, "california")))
    assert fixes == [Correction("Califronia", "california", 0, 10)]


def test_corrected_text_keeps_stopwords_and_appends_phrases() -> None:
    parsed = parse('volatilty in the market "day ahead"')
    fixes = corrections(parsed, _response(_entry("volatilty", 0, "volatility")))
    assert corrected_text(parsed, fixes) == "volatility in the market day ahead"


def test_several_corrections_apply_without_shifting_each_other() -> None:
    parsed = parse("naturl gas piepline")
    response = _response(_entry("naturl", 0, "natural"), _entry("piepline", 11, "pipeline"))
    assert corrected_text(parsed, corrections(parsed, response)) == "natural gas pipeline"


def test_a_response_without_suggestions_corrects_nothing() -> None:
    assert corrections(parse("anything"), {}) == []
