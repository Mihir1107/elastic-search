"""Unit tests for archive scanning / selective extraction (no network)."""

from __future__ import annotations

from pathlib import Path

from ingest.download import _mailbox_of, select_mailboxes
from ingest.parse import select_message_files


def test_mailbox_of_reads_the_owner_directory() -> None:
    assert _mailbox_of("maildir/allen-p/_sent_mail/1.") == "allen-p"
    assert _mailbox_of("maildir/allen-p") is None  # too shallow
    assert _mailbox_of("something-else/allen-p/inbox/1.") is None


def test_select_mailboxes_is_deterministic_and_covers_the_target() -> None:
    counts = {f"user-{i}": 100 for i in range(20)}
    first = select_mailboxes(counts, 450)
    second = select_mailboxes(counts, 450)

    assert first == second, "selection must be reproducible"
    # Whole mailboxes only, so it covers the target without going far past it.
    assert sum(counts[m] for m in first) >= 450
    assert len(first) == 5


def test_select_mailboxes_takes_everything_when_target_exceeds_corpus() -> None:
    counts = {"a": 10, "b": 10}
    assert select_mailboxes(counts, 1000) == {"a", "b"}


def test_extraction_is_a_superset_of_what_parse_selects(tmp_path: Path) -> None:
    """The guarantee download.py relies on: parse never needs a mailbox we skipped."""
    counts = {f"user-{i}": 40 for i in range(12)}
    target = 100
    wanted = select_mailboxes(counts, target)

    # Materialise only the extracted mailboxes, as the real extraction would.
    maildir = tmp_path / "maildir"
    for mailbox in wanted:
        for i in range(counts[mailbox]):
            path = maildir / mailbox / "inbox" / f"{i}."
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("From: a@enron.com\n\nbody\n")

    selected = select_message_files(maildir, "dev", target)
    assert len(selected) == target
    used = {p.relative_to(maildir).parts[0] for p in selected}
    assert used <= wanted, "parse selected a mailbox that was never extracted"
