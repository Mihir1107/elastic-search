"""Parser tests. The parser is the core of the product, so this is exhaustive."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date

import pytest

from app.search.parser import (
    FUZZINESS,
    MAX_QUERY_CHARS,
    MAX_TERMS,
    MAX_VALUES_PER_FIELD,
    ParsedQuery,
    is_address,
    parse,
)

# --------------------------- free text ---------------------------


def test_plain_free_text() -> None:
    q = parse("raptor partnership structure")
    assert q.terms == ("raptor", "partnership", "structure")
    assert q.text == "raptor partnership structure"
    assert q.phrases == ()
    assert q.has_text and not q.has_filters and not q.is_empty


def test_empty_query_is_empty() -> None:
    for raw in ("", "   ", "\t\n"):
        q = parse(raw)
        assert q.is_empty
        assert not q.has_text and not q.has_filters


def test_none_like_input_does_not_raise() -> None:
    assert parse("").raw == ""


# --------------------------- phrases ---------------------------


def test_quoted_phrase_is_separated_from_free_text() -> None:
    q = parse('budget "hiding losses" review')
    assert q.phrases == ("hiding losses",)
    assert q.terms == ("budget", "review")


def test_multiple_phrases() -> None:
    q = parse('"raptor partnership" and "special purpose entity"')
    assert q.phrases == ("raptor partnership", "special purpose entity")
    assert q.terms == ("and",)


def test_unbalanced_quote_is_tolerated_with_a_warning() -> None:
    q = parse('budget "hiding losses')
    assert q.phrases == ("hiding losses",)
    assert any("unbalanced quote" in w for w in q.warnings)


def test_empty_phrase_is_dropped() -> None:
    q = parse('budget ""')
    assert q.phrases == ()
    assert q.terms == ("budget",)


# --------------------------- field operators ---------------------------


def test_from_with_address_is_lowercased() -> None:
    q = parse("from:Kenneth.LAY@enron.com")
    assert q.from_ == ("kenneth.lay@enron.com",)
    assert is_address(q.from_[0])
    assert q.has_filters and not q.has_text


def test_from_with_quoted_display_name() -> None:
    q = parse('from:"Kenneth Lay"')
    assert q.from_ == ("kenneth lay",)
    assert not is_address(q.from_[0])


def test_to_and_cc_operators() -> None:
    q = parse("to:a@enron.com cc:b@enron.com")
    assert q.to == ("a@enron.com",)
    assert q.cc == ("b@enron.com",)


def test_subject_operator_preserves_case() -> None:
    q = parse("subject:Raptor")
    assert q.subject == ("Raptor",)


def test_field_names_are_case_insensitive() -> None:
    q = parse("FROM:a@enron.com To:b@enron.com")
    assert q.from_ == ("a@enron.com",)
    assert q.to == ("b@enron.com",)


def test_repeated_operators_accumulate() -> None:
    q = parse("from:a@enron.com from:b@enron.com")
    assert q.from_ == ("a@enron.com", "b@enron.com")


def test_unknown_operator_becomes_free_text() -> None:
    """An unrecognised prefix must not be silently dropped."""
    q = parse("foo:bar raptor")
    assert "foo:bar" in q.terms
    assert "raptor" in q.terms


def test_empty_operator_value_warns() -> None:
    q = parse("from: raptor")
    assert q.from_ == ()
    assert any("empty from:" in w for w in q.warnings)
    assert q.terms == ("raptor",)


def test_operator_value_cap() -> None:
    raw = " ".join(f"from:user{i}@enron.com" for i in range(MAX_VALUES_PER_FIELD + 4))
    q = parse(raw)
    assert len(q.from_) == MAX_VALUES_PER_FIELD
    assert any("beyond" in w for w in q.warnings)


# --------------------------- dates ---------------------------


def test_date_range_operators() -> None:
    q = parse("after:2001-07-01 before:2001-12-31")
    assert q.after == date(2001, 7, 1)
    assert q.before == date(2001, 12, 31)
    assert q.has_filters


@pytest.mark.parametrize("bad", ["2001/07/01", "July 2001", "2001-13-01", "20010701", "x"])
def test_invalid_dates_are_ignored_with_a_warning(bad: str) -> None:
    q = parse(f"after:{bad}")
    assert q.after is None
    assert any("expected YYYY-MM-DD" in w for w in q.warnings)


def test_inverted_range_warns() -> None:
    q = parse("after:2002-01-01 before:2001-01-01")
    assert any("matches nothing" in w for w in q.warnings)


# --------------------------- safety / limits ---------------------------


def test_wildcard_and_regexp_characters_stay_literal_text() -> None:
    """Flaw #13: these must never reach a wildcard/regexp query."""
    q = parse("ra*tor .*(a|b)+ ?x")
    assert "ra*tor" in q.terms
    assert ".*(a|b)+" in q.terms


def test_overlong_query_is_truncated() -> None:
    q = parse("x" * (MAX_QUERY_CHARS + 50))
    assert len(q.raw) == MAX_QUERY_CHARS + 50  # raw is preserved for echoing back
    assert any("truncated" in w for w in q.warnings)


def test_too_many_terms_are_capped() -> None:
    q = parse(" ".join(f"t{i}" for i in range(MAX_TERMS + 10)))
    assert len(q.terms) == MAX_TERMS
    assert any("first" in w for w in q.warnings)


def test_control_characters_are_stripped() -> None:
    q = parse("rap\x00tor\x07 deal")
    assert "rap" in q.terms and "tor" in q.terms


# --------------------------- derived helpers ---------------------------


def test_semantic_text_includes_phrases() -> None:
    q = parse('raptor "hiding losses"')
    assert q.semantic_text == "raptor hiding losses"


def test_semantic_text_empty_for_filter_only_query() -> None:
    assert parse("from:a@enron.com").semantic_text == ""


def test_fuzziness_only_applies_from_five_characters() -> None:
    q = parse("x")
    assert q.fuzziness_for("deal") is None  # 4 chars -> exact
    assert q.fuzziness_for("raptor") == FUZZINESS  # 6 chars -> fuzzy
    assert q.fuzziness_for("skill") == FUZZINESS  # exactly 5 -> fuzzy


def test_parsed_query_is_hashable_and_frozen() -> None:
    q = parse("raptor")
    assert isinstance(q, ParsedQuery)
    assert hash(q) is not None
    with pytest.raises(FrozenInstanceError):
        q.text = "nope"  # type: ignore[misc]


def test_combined_realistic_query() -> None:
    q = parse(
        'raptor partnership from:kenneth.lay@enron.com to:"Jeff Skilling" '
        '"hiding losses" after:2001-07-01 before:2001-12-31'
    )
    assert q.terms == ("raptor", "partnership")
    assert q.phrases == ("hiding losses",)
    assert q.from_ == ("kenneth.lay@enron.com",)
    assert q.to == ("jeff skilling",)
    assert q.after == date(2001, 7, 1) and q.before == date(2001, 12, 31)
    assert q.warnings == ()
    assert q.has_text and q.has_filters
