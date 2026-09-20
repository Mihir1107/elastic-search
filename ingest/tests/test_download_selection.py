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


def _fake_archive(path: Path, mailboxes: dict[str, int]) -> None:
    """A miniature maildir tarball, shaped like the real CMU release."""
    import io
    import tarfile

    with tarfile.open(path, "w:gz") as tar:
        for mailbox, count in mailboxes.items():
            for i in range(count):
                payload = b"From: a@enron.com\n\nbody\n"
                info = tarfile.TarInfo(f"maildir/{mailbox}/inbox/{i}.")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))


def test_growing_the_dev_subset_re_extracts(tmp_path: Path) -> None:
    """Regression: the marker must carry the subset SIZE, not just its name.

    With only the name in it, raising DEV_SUBSET_SIZE matched the existing marker,
    extraction was skipped, and parse silently selected from the smaller mailbox
    set while every stats file still reported success.
    """
    from ingest.config import IngestSettings
    from ingest.download import download

    mailboxes = {f"user-{i}": 40 for i in range(12)}
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    _fake_archive(raw / "enron.tar.gz", mailboxes)

    def settings_for(target: int) -> IngestSettings:
        return IngestSettings(
            data_dir=tmp_path,
            dev_subset_size=target,
            enron_url="https://example.invalid/enron.tar.gz",
            enron_sha256="",
        )

    download(settings_for(80), subset="dev")
    small = {p.name for p in (raw / "maildir").iterdir()}

    download(settings_for(400), subset="dev")
    large = {p.name for p in (raw / "maildir").iterdir()}

    assert len(small) == 2
    assert small < large, "raising the target must extract more mailboxes"
