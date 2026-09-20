"""Stage 1: download + checksum + extract the Enron corpus.

Idempotent: an archive that is already present is not re-downloaded, and an
already-extracted maildir is not re-extracted. The archive is streamed to a
``.part`` file and renamed only on success, so an interrupted run never leaves a
truncated archive that looks complete.

Source: https://www.cs.cmu.edu/~enron/ (CMU CALO release, May 2015 maildir).
"""

from __future__ import annotations

import hashlib
import tarfile
import urllib.request
from pathlib import Path

from ingest.config import IngestSettings
from ingest.stats import StageStats

_CHUNK = 1024 * 1024
_SENTINEL = ".extracted"


def _stream_download(url: str, dest: Path) -> tuple[int, str]:
    """Stream ``url`` to ``dest``, returning (bytes, sha256). Atomic via .part."""
    digest = hashlib.sha256()
    total = 0
    tmp = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url) as resp, tmp.open("wb") as out:
        while chunk := resp.read(_CHUNK):
            out.write(chunk)
            digest.update(chunk)
            total += len(chunk)
    tmp.replace(dest)
    return total, digest.hexdigest()


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def download(settings: IngestSettings, *, force: bool = False) -> StageStats:
    stats = StageStats("download")
    raw = settings.raw_dir
    raw.mkdir(parents=True, exist_ok=True)
    archive = raw / settings.enron_url.rsplit("/", 1)[-1]

    if archive.exists() and not force:
        stats.skip("archive-already-present")
        size = archive.stat().st_size
        digest = _sha256_of(archive)
    else:
        size, digest = _stream_download(settings.enron_url, archive)
        stats.ok()

    stats.extra["archive"] = str(archive)
    stats.extra["archive_bytes"] = size
    stats.extra["sha256"] = digest

    # If a checksum is pinned in config, enforce it; otherwise report it so it can be pinned.
    if settings.enron_sha256:
        if digest != settings.enron_sha256:
            stats.fail("checksum-mismatch")
            msg = f"checksum mismatch: expected {settings.enron_sha256}, got {digest}"
            raise ValueError(msg)
        stats.extra["checksum_verified"] = True
    else:
        stats.extra["checksum_verified"] = False
        stats.extra["note"] = "enron_sha256 not pinned; set ENRON_SHA256 to enforce it"

    maildir = raw / "maildir"
    sentinel = raw / _SENTINEL
    if sentinel.exists() and maildir.is_dir() and not force:
        stats.skip("already-extracted")
        stats.extra["maildir"] = str(maildir)
        return stats

    extracted = 0
    # Stream mode ("r|gz") reads the archive in a single pass.
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            tar.extract(member, raw, filter="data")
            if member.isfile():
                extracted += 1
    sentinel.write_text(digest + "\n")
    stats.ok()
    stats.extra["extracted_files"] = extracted
    stats.extra["maildir"] = str(maildir)
    return stats
