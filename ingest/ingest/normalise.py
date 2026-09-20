"""Stage 3: normalise addresses and assign ``person_id``.

Addresses are lowercased and de-duplicated while preserving order. ``person_id``
is kept deliberately simple for the MVP (docs/SPEC.md section 4): the exact
normalised sender address, with the X-From display name retained alongside it so
a richer alias map can be layered on later without reindexing the raw fields.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from ingest.stats import StageStats

_ADDRESS_FIELDS = ("to", "cc", "bcc")


def _collapse_ws(value: str) -> str:
    return " ".join(value.split())


def normalise_address(addr: str) -> str:
    return addr.strip().strip("<>").strip().lower()


def dedupe_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def normalise_doc(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out["from"] = normalise_address(str(doc.get("from") or ""))
    for field in _ADDRESS_FIELDS:
        raw = doc.get(field) or []
        out[field] = dedupe_preserve_order(normalise_address(str(a)) for a in raw)
    out["from_name"] = _collapse_ws(str(doc.get("from_name") or ""))
    out["subject"] = _collapse_ws(str(doc.get("subject") or ""))
    out["person_id"] = out["from"]
    return out


def normalise_all(docs: Iterable[dict[str, Any]], stats: StageStats) -> Iterator[dict[str, Any]]:
    for doc in docs:
        out = normalise_doc(doc)
        if not out["from"]:
            stats.skip("from-missing")
        if not (out["to"] or out["cc"] or out["bcc"]):
            stats.skip("no-recipients")
        stats.ok()
        yield out


def run(in_path: Path, out_path: Path) -> StageStats:
    from ingest.jsonl import read_jsonl, write_jsonl

    stats = StageStats("normalise")
    written = write_jsonl(out_path, normalise_all(read_jsonl(in_path), stats))
    stats.extra["written"] = written
    stats.extra["output"] = str(out_path)
    return stats
