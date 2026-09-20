"""Stage 4: collapse the same message appearing in many mailboxes.

The canonical ``_id`` is a SHA-1 over (from, sorted recipients, date, subject,
body). Duplicates merge into one document carrying every ``mailboxes`` /
``folder`` / ``source_paths`` value it was seen under, which is what makes the
whole pipeline idempotent: re-running simply upserts the same ids.

Note: this holds one entry per unique message in memory. That is comfortable for
the 10k dev subset and workable for the full corpus on this machine; a
disk-backed external sort would be the upgrade if memory ever becomes the limit.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ingest.stats import StageStats


def canonical_id(doc: dict[str, Any]) -> str:
    recipients = sorted([*(doc.get("to") or []), *(doc.get("cc") or []), *(doc.get("bcc") or [])])
    key = "\n".join(
        [
            str(doc.get("from") or ""),
            ",".join(recipients),
            str(doc.get("date") or ""),
            str(doc.get("subject") or "").strip(),
            str(doc.get("body") or "").strip(),
        ]
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def dedupe(docs: Iterable[dict[str, Any]], stats: StageStats) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for doc in docs:
        doc_id = canonical_id(doc)
        existing = merged.get(doc_id)
        mailbox = str(doc.get("mailbox") or "")
        folder = str(doc.get("folder") or "")
        source = str(doc.get("source_path") or "")
        if existing is None:
            out = dict(doc)
            out.pop("mailbox", None)
            out.pop("source_path", None)
            out["id"] = doc_id
            out["mailboxes"] = [mailbox] if mailbox else []
            out["folder"] = [folder] if folder else []
            out["source_paths"] = [source] if source else []
            out["duplicate_count"] = 1
            merged[doc_id] = out
            stats.ok()
            continue
        if mailbox and mailbox not in existing["mailboxes"]:
            existing["mailboxes"].append(mailbox)
        if folder and folder not in existing["folder"]:
            existing["folder"].append(folder)
        if source and source not in existing["source_paths"]:
            existing["source_paths"].append(source)
        existing["duplicate_count"] += 1
        stats.skip("duplicate-merged")
    return list(merged.values())


def run(in_path: Path, out_path: Path) -> StageStats:
    from ingest.jsonl import read_jsonl, write_jsonl

    stats = StageStats("dedupe")
    docs = dedupe(read_jsonl(in_path), stats)
    written = write_jsonl(out_path, docs)
    stats.extra["unique_documents"] = written
    stats.extra["output"] = str(out_path)
    return stats
