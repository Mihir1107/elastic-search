"""Unit tests for tag validation and CSV export safety (no cluster needed)."""

from __future__ import annotations

import pytest

from app.routes.export import _cell, _csv_line
from app.tags import MAX_TAGS_PER_EMAIL, TagError, normalise_tags


def test_tags_are_lowercased_trimmed_deduplicated_and_sorted() -> None:
    assert normalise_tags([" Hot", "relevant", "HOT"]) == ["hot", "relevant"]


@pytest.mark.parametrize("bad", ["", "has space", "-leading-dash", "x" * 33, "semi;colon"])
def test_malformed_tags_are_rejected(bad: str) -> None:
    with pytest.raises(TagError):
        normalise_tags([bad])


def test_an_email_carries_a_bounded_number_of_tags() -> None:
    with pytest.raises(TagError):
        normalise_tags([f"t{i}" for i in range(MAX_TAGS_PER_EMAIL + 1)])


@pytest.mark.parametrize("dangerous", ['=HYPERLINK("x")', "+1", "-2+3", "@SUM(A1)", "\tx"])
def test_cells_that_a_spreadsheet_would_execute_are_neutralised(dangerous: str) -> None:
    assert _cell(dangerous) == "'" + dangerous


def test_lists_join_and_none_is_empty() -> None:
    assert _cell(["a@enron.com", "b@enron.com"]) == "a@enron.com; b@enron.com"
    assert _cell(None) == ""


def test_csv_lines_quote_commas_and_newlines() -> None:
    assert _csv_line(["a,b", "line\nbreak", 3]) == '"a,b","line\nbreak",3\r\n'
