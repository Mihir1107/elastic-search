"""Display-name cleaning, driven by what X-From actually contains in this corpus."""

from __future__ import annotations

import pytest

from app.names import display_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # A Lotus Notes distinguished name must never reach the screen.
        ("Hall, Steve C. </O=ENRON/OU=NA/CN=RECIPIENTS/CN=SHALL>", "Steve C. Hall"),
        ('"Neeley, Myrna" <MNeeley@caiso.com>', "Myrna Neeley"),
        ("Phillip K Allen", "Phillip K Allen"),
        ("Williams III, Bill <bill.williams@enron.com>", "Bill Williams III"),
        ("  spaced   out  ", "spaced out"),
    ],
)
def test_names_are_cleaned_for_display(raw: str, expected: str) -> None:
    assert display_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "john.arnold@enron.com",  # an address is not a name
        "/O=ENRON/OU=NA/CN=RECIPIENTS/CN=SHALL",  # a bare DN
        "<only@an.address>",
    ],
)
def test_non_names_return_empty_so_the_ui_can_fall_back(raw: str) -> None:
    assert display_name(raw) == ""


def test_only_a_single_comma_is_treated_as_last_first() -> None:
    # Three parts is a list, not "Last, First"; leave it alone.
    assert display_name("Smith, John, Jr") == "Smith, John, Jr"


def test_absurdly_long_names_are_capped() -> None:
    assert len(display_name("x" * 500)) <= 64
