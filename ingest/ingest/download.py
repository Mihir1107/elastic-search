"""Stage 1: download + checksum + extract the Enron corpus.

Resumable and idempotent (docs/SPEC.md section 4):

* the archive streams to a ``.part`` file and is renamed only on success, and a
  restart continues from what is already on disk via an HTTP Range request, so
  an interrupted 423 MB download is never repeated from zero;
* extraction is **selective**. For the dev subset only the mailboxes that subset
  needs are unpacked (tens of MB) instead of the full ~1.4 GB maildir, which
  matters a great deal on a laptop that is short on disk. Mailboxes are chosen
  with the same stable sha1 ordering ``ingest.parse`` uses, so what is extracted
  is always a superset of what parse will select.

Source: https://www.cs.cmu.edu/~enron/ (CMU CALO release, May 2015 maildir).
"""

from __future__ import annotations

import hashlib
import tarfile
import urllib.error
import urllib.request
from pathlib import Path

from ingest.config import IngestSettings
from ingest.stats import StageStats

_CHUNK = 1024 * 1024
_SENTINEL = ".extracted"
_ROOT = "maildir"


def _stream_download(url: str, dest: Path) -> tuple[int, bool]:
    """Download ``url`` to ``dest``, resuming a partial ``.part`` file.

    Returns (bytes_on_disk, resumed).
    """
    tmp = dest.with_name(dest.name + ".part")
    existing = tmp.stat().st_size if tmp.exists() else 0
    request = urllib.request.Request(url)
    if existing:
        request.add_header("Range", f"bytes={existing}-")

    try:
        with urllib.request.urlopen(request) as response:
            mode = "ab" if existing and response.status == 206 else "wb"
            if mode == "wb":
                existing = 0  # server ignored the Range header; start over
            with tmp.open(mode) as out:
                while chunk := response.read(_CHUNK):
                    out.write(chunk)
    except urllib.error.HTTPError as exc:
        # 416 means the .part file is already the whole archive.
        if exc.code != 416 or not existing:
            raise

    tmp.replace(dest)
    return dest.stat().st_size, existing > 0


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _mailbox_of(member_name: str) -> str | None:
    """Mailbox owner for a *message file* member (maildir/<owner>/<folder>/<file>)."""
    parts = Path(member_name).parts
    if len(parts) < 3 or parts[0] != _ROOT:
        return None
    return parts[1]


def _member_mailbox(member_name: str) -> str | None:
    """Mailbox owner for any member, including the owner directory itself."""
    parts = Path(member_name).parts
    if len(parts) < 2 or parts[0] != _ROOT:
        return None
    return parts[1]


def scan_mailboxes(archive: Path) -> dict[str, int]:
    """One streaming pass over the archive: message count per mailbox."""
    counts: dict[str, int] = {}
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            mailbox = _mailbox_of(member.name)
            if mailbox:
                counts[mailbox] = counts.get(mailbox, 0) + 1
    return counts


def select_mailboxes(counts: dict[str, int], target: int) -> set[str]:
    """Whole mailboxes in stable hash order until ``target`` messages are covered.

    Mirrors ``ingest.parse.select_message_files`` so extraction is a superset of
    what parse will later select.
    """
    ordered = sorted(counts, key=lambda n: hashlib.sha1(n.encode()).hexdigest())
    chosen: set[str] = set()
    total = 0
    for name in ordered:
        if total >= target:
            break
        chosen.add(name)
        total += counts[name]
    return chosen


def extract(archive: Path, raw: Path, wanted: set[str] | None) -> int:
    """Extract the archive. ``wanted`` limits it to those mailboxes (None = all)."""
    extracted = 0
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            if wanted is not None:
                # Applies to directories too, so unwanted mailboxes leave no empty
                # husks behind. Intermediate dirs are created by extract() anyway.
                mailbox = _member_mailbox(member.name)
                if mailbox is None or mailbox not in wanted:
                    continue
            tar.extract(member, raw, filter="data")
            if member.isfile():
                extracted += 1
    return extracted


def download(
    settings: IngestSettings,
    *,
    force: bool = False,
    subset: str = "dev",
    prune_archive: bool = False,
) -> StageStats:
    stats = StageStats("download")
    raw = settings.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    archive = raw / settings.enron_url.rsplit("/", 1)[-1]

    if archive.exists() and not force:
        stats.skip("archive-already-present")
        size = archive.stat().st_size
    else:
        size, resumed = _stream_download(settings.enron_url, archive)
        stats.ok()
        stats.extra["resumed"] = resumed

    digest = _sha256_of(archive)
    stats.extra["archive"] = str(archive)
    stats.extra["archive_bytes"] = size
    stats.extra["sha256"] = digest

    if settings.enron_sha256:
        if digest != settings.enron_sha256:
            stats.fail("checksum-mismatch")
            msg = f"checksum mismatch: expected {settings.enron_sha256}, got {digest}"
            raise ValueError(msg)
        stats.extra["checksum_verified"] = True
    else:
        stats.extra["checksum_verified"] = False
        stats.extra["note"] = "enron_sha256 not pinned; set ENRON_SHA256 to enforce it"

    maildir = raw / _ROOT
    sentinel = raw / _SENTINEL
    # The marker records the subset *and its size*. A dev run with a larger
    # DEV_SUBSET_SIZE needs more mailboxes on disk, and with only the subset name
    # in the marker that re-extraction is silently skipped -- leaving parse to
    # select from the smaller mailbox set while reporting success.
    scope = subset if subset == "full" else f"{subset}:{settings.dev_subset_size}"
    expected_marker = f"{digest}:{scope}"
    if (
        sentinel.exists()
        and maildir.is_dir()
        and sentinel.read_text().strip() == expected_marker
        and not force
    ):
        stats.skip("already-extracted")
        stats.extra["maildir"] = str(maildir)
        return stats

    wanted: set[str] | None = None
    if subset != "full":
        counts = scan_mailboxes(archive)
        stats.extra["mailboxes_in_archive"] = len(counts)
        stats.extra["messages_in_archive"] = sum(counts.values())
        wanted = select_mailboxes(counts, settings.dev_subset_size)
        stats.extra["mailboxes_extracted"] = sorted(wanted)

    extracted = extract(archive, raw, wanted)
    sentinel.write_text(expected_marker + "\n")
    stats.ok()
    stats.extra["subset"] = subset
    stats.extra["extracted_files"] = extracted
    stats.extra["maildir"] = str(maildir)

    if prune_archive:
        archive.unlink(missing_ok=True)
        stats.extra["archive_pruned"] = True

    return stats
